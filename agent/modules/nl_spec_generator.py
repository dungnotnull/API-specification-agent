"""NLSpecGenerator — natural language → OpenAPI 3.0 YAML; code → spec via CodeT5+."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)

NL_TO_SPEC_PROMPT = """You are an expert API designer. Generate a complete, valid OpenAPI 3.0.3 YAML specification from the user's natural language description.

Requirements:
- Include ALL likely status codes: 200/201/400/401/403/404/422/500 (use only applicable ones per endpoint)
- Define a reusable Error schema in components/schemas/Error following RFC 7807 (type, title, status, detail fields)
- Add authentication: JWT Bearer security scheme unless explicitly stated otherwise
- Write non-empty descriptions for every path, operation, and parameter
- Include at least one request body example and one response example per operation
- Use proper HTTP methods: GET for reads, POST for creates, PUT/PATCH for updates, DELETE for deletes
- Set info.title, info.description, info.version
- Set servers[0].url to the provided base URL

Output ONLY valid OpenAPI 3.0.3 YAML. No markdown code fences. No extra explanation."""

CODE_REVERSE_PROMPT = """You are an expert API analyst. Analyze the following {language} source code and extract an OpenAPI 3.0.3 specification.

Look for:
- HTTP route decorators/annotations (Flask @app.route, Express router.get, Gin r.GET, etc.)
- Request body schemas (Pydantic models, Joi schemas, Go structs)
- Response schemas and status codes
- Authentication middleware
- Path parameters, query parameters, header parameters

Output ONLY valid OpenAPI 3.0.3 YAML. No markdown. No explanation."""

PATCH_SPEC_PROMPT = """You are an OpenAPI expert. The following OpenAPI 3.0 spec has validation errors.
Fix ALL listed issues and return the corrected complete spec.

Issues to fix:
{issues}

Output ONLY the corrected complete OpenAPI 3.0.3 YAML."""


class GenerationResult:
    def __init__(self, spec: dict, spec_yaml: str, confidence: float, warnings: list[str]):
        self.spec = spec
        self.spec_yaml = spec_yaml
        self.confidence = confidence
        self.warnings = warnings

    def to_dict(self) -> dict:
        return {
            "spec": self.spec,
            "spec_yaml": self.spec_yaml,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }


class NLSpecGenerator:
    """
    Generates OpenAPI 3.0 YAML from natural language or source code.

    Primary path: LLM (Claude) → YAML parse → schema validation → retry if invalid
    Fallback: template-based spec with placeholder values
    Reverse path: CodeT5+ code analysis → LLM enhancement → YAML
    """

    def __init__(self):
        self._llm = None
        self._hf = None

    def _get_llm(self):
        if self._llm is None:
            import sys
            sys.path.insert(0, str(ROOT))
            from tools.llm_client import UnifiedLLMClient
            self._llm = UnifiedLLMClient()
        return self._llm

    def _get_hf(self):
        if self._hf is None:
            import sys
            sys.path.insert(0, str(ROOT))
            from tools.hf_model_manager import HFModelManager
            self._hf = HFModelManager.instance()
        return self._hf

    async def generate_from_nl(
        self,
        description: str,
        existing_schemas: dict = None,
        base_url: str = "https://api.example.com/v1",
        api_version: str = "1.0.0",
    ) -> dict:
        """Generate OpenAPI spec from natural language description."""
        context_schemas_json = json.dumps(existing_schemas or {}, indent=2)

        user_msg = (
            f"API description: {description}\n\n"
            f"Base URL: {base_url}\n"
            f"API version: {api_version}\n"
            f"Existing component schemas (re-use these): {context_schemas_json}"
        )

        for attempt in range(3):
            try:
                raw = await self._get_llm().complete(
                    system=NL_TO_SPEC_PROMPT,
                    user=user_msg,
                    task="nl_spec_generation",
                    max_tokens=4096,
                )
                raw = self._strip_fences(raw)
                spec = yaml.safe_load(raw)
                if not isinstance(spec, dict):
                    raise ValueError("Parsed YAML is not a dict")

                confidence = self._estimate_confidence(spec)
                warnings = self._collect_warnings(spec)

                return GenerationResult(
                    spec=spec,
                    spec_yaml=yaml.dump(spec, sort_keys=False, allow_unicode=True),
                    confidence=confidence,
                    warnings=warnings,
                ).to_dict()

            except Exception as e:
                logger.warning("NL generation attempt %d failed: %s", attempt + 1, e)
                user_msg += f"\n\nPrevious attempt failed with error: {e}. Please fix."

        # Fallback: minimal template
        logger.error("All NL generation attempts failed; returning template spec")
        return self._template_spec(description, base_url, api_version)

    async def generate_from_code(
        self,
        code: str,
        language: str = "python",
        base_url: str = "https://api.example.com/v1",
    ) -> dict:
        """Reverse-engineer OpenAPI spec from source code using CodeT5+ + LLM."""
        # Step 1: CodeT5+ code summary (extract route info)
        code_summary = self._codet5_extract_routes(code, language)

        # Step 2: LLM generates full spec from code + summary
        user_msg = (
            f"Language: {language}\n"
            f"Base URL: {base_url}\n\n"
            f"CodeT5+ extracted route info:\n{code_summary}\n\n"
            f"Full source code:\n```{language}\n{code[:6000]}\n```"
        )

        prompt = CODE_REVERSE_PROMPT.format(language=language)

        for attempt in range(3):
            try:
                raw = await self._get_llm().complete(
                    system=prompt,
                    user=user_msg,
                    task="code_reverse_spec",
                    max_tokens=4096,
                )
                raw = self._strip_fences(raw)
                spec = yaml.safe_load(raw)
                if not isinstance(spec, dict):
                    raise ValueError("Parsed YAML is not a dict")

                confidence = self._estimate_confidence(spec) * 0.85  # slight penalty for reverse
                warnings = self._collect_warnings(spec)
                warnings.append("Generated by reverse engineering — review for completeness")

                return GenerationResult(
                    spec=spec,
                    spec_yaml=yaml.dump(spec, sort_keys=False, allow_unicode=True),
                    confidence=confidence,
                    warnings=warnings,
                ).to_dict()

            except Exception as e:
                logger.warning("Code reverse attempt %d failed: %s", attempt + 1, e)

        return self._template_spec(f"Reverse-engineered from {language} code", base_url)

    async def patch_spec(self, spec: dict, issues: list[dict]) -> dict:
        """Patch an existing spec to fix validation issues."""
        issue_summary = "\n".join(
            f"- [{i.get('severity','?')}] {i.get('gate','?')}: {i.get('message','')}"
            for i in issues
            if i.get("severity") == "ERROR"
        )

        spec_yaml = yaml.dump(spec, sort_keys=False, allow_unicode=True)
        user_msg = f"Current spec:\n{spec_yaml}\n\nIssues:\n{issue_summary}"

        prompt = PATCH_SPEC_PROMPT.format(issues=issue_summary)

        try:
            raw = await self._get_llm().complete(
                system=prompt,
                user=user_msg,
                task="spec_patch",
                max_tokens=4096,
            )
            raw = self._strip_fences(raw)
            patched = yaml.safe_load(raw)
            if not isinstance(patched, dict):
                raise ValueError("Patched YAML is not a dict")
            return GenerationResult(
                spec=patched,
                spec_yaml=yaml.dump(patched, sort_keys=False, allow_unicode=True),
                confidence=self._estimate_confidence(patched),
                warnings=["Spec was automatically patched to fix validation errors"],
            ).to_dict()
        except Exception as e:
            logger.error("patch_spec failed: %s", e)
            return GenerationResult(
                spec=spec,
                spec_yaml=spec_yaml,
                confidence=0.5,
                warnings=[f"Patch failed: {e}"],
            ).to_dict()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _codet5_extract_routes(self, code: str, language: str) -> str:
        """Use CodeT5+ to summarize code and extract route definitions."""
        try:
            hf = self._get_hf()
            summary = hf.analyze_code(code[:4096], task="summarize")
            return summary or self._regex_extract_routes(code, language)
        except Exception as e:
            logger.warning("CodeT5+ extraction failed: %s", e)
            return self._regex_extract_routes(code, language)

    def _regex_extract_routes(self, code: str, language: str) -> str:
        """Simple regex fallback to extract route definitions from code."""
        import re
        patterns = {
            "python": [
                r'@(?:app|router|blueprint)\.(get|post|put|patch|delete|options)\(["\']([^"\']+)["\']',
                r'@(?:app|router)\.(route)\(["\']([^"\']+)["\']',
            ],
            "javascript": [
                r'router\.(get|post|put|patch|delete)\(["\']([^"\']+)["\']',
                r'app\.(get|post|put|patch|delete)\(["\']([^"\']+)["\']',
            ],
            "go": [
                r'r\.(GET|POST|PUT|PATCH|DELETE)\(["\']([^"\']+)["\']',
                r'router\.(HandleFunc|Handle)\(["\']([^"\']+)["\']',
            ],
        }

        routes = []
        for pattern in patterns.get(language, patterns["python"]):
            for m in re.finditer(pattern, code, re.IGNORECASE):
                method = m.group(1).upper()
                path = m.group(2)
                routes.append(f"{method} {path}")

        if routes:
            return "Detected routes:\n" + "\n".join(f"  - {r}" for r in routes)
        return "No routes detected via regex; relying on LLM analysis."

    def _estimate_confidence(self, spec: dict) -> float:
        """Heuristic confidence estimate based on spec completeness."""
        score = 0.0
        if spec.get("openapi"):
            score += 0.2
        if spec.get("info", {}).get("title"):
            score += 0.1
        paths = spec.get("paths", {})
        if paths:
            score += 0.3
            ops = sum(len([m for m in p.values() if isinstance(p, dict)]) for p in paths.values() if isinstance(p, dict))
            if ops >= 2:
                score += 0.2
        if spec.get("components", {}).get("schemas"):
            score += 0.1
        if spec.get("components", {}).get("securitySchemes"):
            score += 0.1
        return min(score, 1.0)

    def _collect_warnings(self, spec: dict) -> list[str]:
        warnings = []
        if not spec.get("components", {}).get("securitySchemes"):
            warnings.append("No security schemes defined; add authentication if required")
        paths = spec.get("paths", {})
        for path, path_item in (paths.items() if isinstance(paths, dict) else []):
            if not isinstance(path_item, dict):
                continue
            for method, op in path_item.items():
                if not isinstance(op, dict):
                    continue
                responses = op.get("responses", {})
                codes = list(responses.keys())
                has_4xx = any(str(c).startswith("4") for c in codes)
                if not has_4xx:
                    warnings.append(f"No 4xx response on {method.upper()} {path}")
        return warnings

    def _strip_fences(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            text = "\n".join(lines[start:end])
        return text

    def _template_spec(self, description: str, base_url: str, version: str = "1.0.0") -> dict:
        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "Generated API",
                "description": description,
                "version": version,
            },
            "servers": [{"url": base_url}],
            "paths": {
                "/resource": {
                    "get": {
                        "summary": "List resources",
                        "description": "Returns a list of resources.",
                        "operationId": "listResources",
                        "responses": {
                            "200": {
                                "description": "Successful response",
                                "content": {
                                    "application/json": {
                                        "schema": {"type": "array", "items": {"type": "object"}}
                                    }
                                },
                            },
                            "500": {"$ref": "#/components/responses/InternalError"},
                        },
                    }
                }
            },
            "components": {
                "schemas": {
                    "Error": {
                        "type": "object",
                        "required": ["type", "title", "status"],
                        "properties": {
                            "type": {"type": "string"},
                            "title": {"type": "string"},
                            "status": {"type": "integer"},
                            "detail": {"type": "string"},
                        },
                    }
                },
                "responses": {
                    "InternalError": {
                        "description": "Internal server error",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        },
                    }
                },
                "securitySchemes": {
                    "BearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                    }
                },
            },
        }
        return GenerationResult(
            spec=spec,
            spec_yaml=yaml.dump(spec, sort_keys=False, allow_unicode=True),
            confidence=0.3,
            warnings=["Template spec used — LLM generation failed. Review and complete manually."],
        ).to_dict()
