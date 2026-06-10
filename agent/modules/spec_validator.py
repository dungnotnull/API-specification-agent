"""SpecValidator — 7-gate OpenAPI 3.0 completeness and best-practice checker."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)

VALIDATION_EXPLANATION_PROMPT = """You are an OpenAPI spec reviewer. For each validation issue below,
provide a concise explanation (2 sentences max) and a minimal YAML snippet that fixes it.

Return JSON array: [{"issue_id": "...", "explanation": "...", "yaml_fix": "..."}]

Issues:
{issues}

Spec excerpt (relevant paths):
{spec_excerpt}"""


@dataclass
class ValidationIssue:
    gate: str
    severity: Literal["ERROR", "WARN", "INFO"]
    path: str
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "gate": self.gate,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
            "suggestion": self.suggestion,
        }


GATES = [
    "STATUS_CODES",
    "ERROR_SCHEMAS",
    "AUTH_COVERAGE",
    "DESCRIPTIONS",
    "EXAMPLES",
    "VERSIONING",
    "SECURITY_SCHEMES",
]


class SpecValidator:
    """
    Validates OpenAPI 3.0 specs against 7 completeness gates.

    ERROR gates: block spec export
    WARN gates: included in report but do not block
    INFO gates: informational only
    """

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            import sys
            sys.path.insert(0, str(ROOT))
            from tools.llm_client import UnifiedLLMClient
            self._llm = UnifiedLLMClient()
        return self._llm

    async def validate(self, spec: dict, generate_explanations: bool = False) -> dict:
        """
        Run all 7 gates against the spec.

        Args:
            spec: OpenAPI spec dict
            generate_explanations: If True, use LLM to generate explanations for issues

        Returns dict: score, issues, report_md, passed_gates, failed_gates, failed_error_gates
        """
        issues: list[ValidationIssue] = []

        # Run schema-level validation first
        schema_issues = self._validate_openapi_schema(spec)
        issues.extend(schema_issues)

        # Run 7 content gates
        issues.extend(self._gate_status_codes(spec))
        issues.extend(self._gate_error_schemas(spec))
        issues.extend(self._gate_auth_coverage(spec))
        issues.extend(self._gate_descriptions(spec))
        issues.extend(self._gate_examples(spec))
        issues.extend(self._gate_versioning(spec))
        issues.extend(self._gate_security_schemes(spec))

        # Score: gates passed / 7
        failed_gates = list({i.gate for i in issues if i.severity == "ERROR"})
        passed_gates = [g for g in GATES if g not in failed_gates]
        score = len(passed_gates) / len(GATES)

        # Generate LLM explanations for issues if requested
        if generate_explanations and issues:
            await self._enrich_issues_with_explanations(spec, issues)

        issues_dicts = [i.to_dict() for i in issues]

        report_md = self._build_report(spec, score, issues, passed_gates, failed_gates)

        return {
            "score": score,
            "issues": issues_dicts,
            "report_md": report_md,
            "passed_gates": passed_gates,
            "failed_gates": [g for g in GATES if g in failed_gates],
            "failed_error_gates": [g for g in GATES if g in failed_gates],
        }

    # ── Gate implementations ──────────────────────────────────────────────────

    def _validate_openapi_schema(self, spec: dict) -> list[ValidationIssue]:
        issues = []
        try:
            from openapi_spec_validator import validate as oas_validate
            from openapi_spec_validator.readers import read_from_filename
            oas_validate(spec)
        except ImportError:
            pass  # openapi-spec-validator not installed; skip
        except Exception as e:
            issues.append(ValidationIssue(
                gate="SCHEMA",
                severity="ERROR",
                path="",
                message=f"OpenAPI schema validation error: {e}",
                suggestion="Ensure spec conforms to OpenAPI 3.0.3 schema",
            ))
        return issues

    def _gate_status_codes(self, spec: dict) -> list[ValidationIssue]:
        """Gate: every operation must have ≥1 2xx response AND ≥1 4xx response."""
        issues = []
        for path, path_item in (spec.get("paths") or {}).items():
            if not isinstance(path_item, dict):
                continue
            for method in ("get", "post", "put", "patch", "delete", "head", "options"):
                op = path_item.get(method)
                if not isinstance(op, dict):
                    continue
                responses = op.get("responses") or {}
                codes = [str(c) for c in responses.keys()]
                has_2xx = any(c.startswith("2") or c == "default" for c in codes)
                has_4xx = any(c.startswith("4") for c in codes)

                if not has_2xx:
                    issues.append(ValidationIssue(
                        gate="STATUS_CODES",
                        severity="ERROR",
                        path=f"paths.{path}.{method}",
                        message=f"{method.upper()} {path}: no 2xx success response defined",
                        suggestion="Add a 200 or 201 response with schema",
                    ))
                if not has_4xx:
                    issues.append(ValidationIssue(
                        gate="STATUS_CODES",
                        severity="WARN",
                        path=f"paths.{path}.{method}",
                        message=f"{method.upper()} {path}: no 4xx client error response defined",
                        suggestion="Add 400/401/404/422 responses as applicable",
                    ))
        return issues

    def _gate_error_schemas(self, spec: dict) -> list[ValidationIssue]:
        """Gate: all 4xx/5xx responses must reference a defined error schema."""
        issues = []
        schemas = (spec.get("components") or {}).get("schemas") or {}
        has_error_schema = "Error" in schemas or "ProblemDetail" in schemas or "ErrorResponse" in schemas

        if not has_error_schema:
            issues.append(ValidationIssue(
                gate="ERROR_SCHEMAS",
                severity="ERROR",
                path="components.schemas",
                message="No reusable error schema defined (expected: Error, ProblemDetail, or ErrorResponse)",
                suggestion='Add components/schemas/Error with RFC 7807 fields: type, title, status, detail',
            ))
            return issues

        for path, path_item in (spec.get("paths") or {}).items():
            if not isinstance(path_item, dict):
                continue
            for method, op in path_item.items():
                if not isinstance(op, dict) or method.startswith("x-"):
                    continue
                responses = op.get("responses") or {}
                for code, resp in responses.items():
                    if not str(code).startswith(("4", "5")):
                        continue
                    if isinstance(resp, dict) and "$ref" not in resp:
                        content = resp.get("content") or {}
                        has_schema = any(
                            (m.get("schema") or {}).get("$ref")
                            for m in content.values()
                            if isinstance(m, dict)
                        )
                        if not has_schema:
                            issues.append(ValidationIssue(
                                gate="ERROR_SCHEMAS",
                                severity="WARN",
                                path=f"paths.{path}.{method}.responses.{code}",
                                message=f"{method.upper()} {path} {code}: error response has no schema $ref",
                                suggestion="Use $ref: '#/components/responses/Error' or inline the Error schema",
                            ))
        return issues

    def _gate_auth_coverage(self, spec: dict) -> list[ValidationIssue]:
        """Gate: global or per-operation security scheme must be present."""
        issues = []
        global_security = spec.get("security")
        security_schemes = (spec.get("components") or {}).get("securitySchemes") or {}

        if not security_schemes:
            issues.append(ValidationIssue(
                gate="AUTH_COVERAGE",
                severity="ERROR",
                path="components.securitySchemes",
                message="No security schemes defined",
                suggestion="Add BearerAuth JWT scheme or API key scheme in components/securitySchemes",
            ))
            return issues

        if not global_security:
            # Check per-operation
            all_ops_have_security = True
            for path, path_item in (spec.get("paths") or {}).items():
                if not isinstance(path_item, dict):
                    continue
                for method, op in path_item.items():
                    if not isinstance(op, dict) or method.startswith("x-"):
                        continue
                    if "security" not in op:
                        all_ops_have_security = False
                        break

            if not all_ops_have_security:
                issues.append(ValidationIssue(
                    gate="AUTH_COVERAGE",
                    severity="WARN",
                    path="root.security",
                    message="No global security field; some operations may lack auth coverage",
                    suggestion="Add a global security field or per-operation security on each path",
                ))
        return issues

    def _gate_descriptions(self, spec: dict) -> list[ValidationIssue]:
        """Gate: all paths/operations/parameters must have non-empty descriptions."""
        issues = []
        for path, path_item in (spec.get("paths") or {}).items():
            if not isinstance(path_item, dict):
                continue
            for method, op in path_item.items():
                if not isinstance(op, dict) or method.startswith("x-"):
                    continue
                if not op.get("description") and not op.get("summary"):
                    issues.append(ValidationIssue(
                        gate="DESCRIPTIONS",
                        severity="WARN",
                        path=f"paths.{path}.{method}",
                        message=f"{method.upper()} {path}: missing description/summary",
                        suggestion="Add a summary (short) and description (detailed) to every operation",
                    ))
                for param in (op.get("parameters") or []):
                    if isinstance(param, dict) and not param.get("description") and "$ref" not in param:
                        issues.append(ValidationIssue(
                            gate="DESCRIPTIONS",
                            severity="INFO",
                            path=f"paths.{path}.{method}.parameters[{param.get('name','')}]",
                            message=f"Parameter '{param.get('name','')}' has no description",
                            suggestion="Add a description field to each parameter",
                        ))
        return issues

    def _gate_examples(self, spec: dict) -> list[ValidationIssue]:
        """Gate: at least one request/response example per operation."""
        issues = []
        for path, path_item in (spec.get("paths") or {}).items():
            if not isinstance(path_item, dict):
                continue
            for method, op in path_item.items():
                if not isinstance(op, dict) or method.startswith("x-"):
                    continue
                has_example = False
                # Check request body
                req_body = op.get("requestBody") or {}
                for media_obj in (req_body.get("content") or {}).values():
                    if isinstance(media_obj, dict) and (media_obj.get("example") or media_obj.get("examples")):
                        has_example = True
                # Check responses
                for resp in (op.get("responses") or {}).values():
                    if isinstance(resp, dict):
                        for media_obj in (resp.get("content") or {}).values():
                            if isinstance(media_obj, dict) and (media_obj.get("example") or media_obj.get("examples")):
                                has_example = True

                if not has_example:
                    issues.append(ValidationIssue(
                        gate="EXAMPLES",
                        severity="WARN",
                        path=f"paths.{path}.{method}",
                        message=f"{method.upper()} {path}: no request/response examples defined",
                        suggestion="Add an 'example' field to at least one request body or response content",
                    ))
        return issues

    def _gate_versioning(self, spec: dict) -> list[ValidationIssue]:
        """Gate: API version declared in info.version."""
        issues = []
        info = spec.get("info") or {}
        if not info.get("version"):
            issues.append(ValidationIssue(
                gate="VERSIONING",
                severity="ERROR",
                path="info.version",
                message="info.version is missing",
                suggestion="Set info.version to a semver string, e.g. '1.0.0'",
            ))
        elif not info.get("title"):
            issues.append(ValidationIssue(
                gate="VERSIONING",
                severity="WARN",
                path="info.title",
                message="info.title is missing",
                suggestion="Set a meaningful info.title for your API",
            ))
        return issues

    def _gate_security_schemes(self, spec: dict) -> list[ValidationIssue]:
        """Gate: declared security scheme names must match definitions."""
        issues = []
        security_schemes = (spec.get("components") or {}).get("securitySchemes") or {}
        if not security_schemes:
            return issues  # covered by AUTH_COVERAGE gate

        all_declared = set()
        global_sec = spec.get("security") or []
        for s in global_sec:
            all_declared.update(s.keys())

        for path, path_item in (spec.get("paths") or {}).items():
            if not isinstance(path_item, dict):
                continue
            for method, op in path_item.items():
                if not isinstance(op, dict) or method.startswith("x-"):
                    continue
                for s in (op.get("security") or []):
                    all_declared.update(s.keys())

        for name in all_declared:
            if name not in security_schemes:
                issues.append(ValidationIssue(
                    gate="SECURITY_SCHEMES",
                    severity="ERROR",
                    path=f"components.securitySchemes.{name}",
                    message=f"Security scheme '{name}' is used but not defined in components/securitySchemes",
                    suggestion=f"Add '{name}' to components/securitySchemes or fix the reference",
                ))
        return issues

    # ── Report builder ────────────────────────────────────────────────────────

    def _build_report(
        self,
        spec: dict,
        score: float,
        issues: list[ValidationIssue],
        passed_gates: list[str],
        failed_gates: list[str],
    ) -> str:
        lines = [
            "# OpenAPI Spec Validation Report",
            "",
            f"**Completeness Score:** {score:.0%}",
            f"**Passed Gates:** {', '.join(passed_gates) or 'none'}",
            f"**Failed Gates:** {', '.join(failed_gates) or 'none'}",
            "",
        ]

        title = (spec.get("info") or {}).get("title", "Unknown API")
        version = (spec.get("info") or {}).get("version", "?")
        path_count = len(spec.get("paths") or {})
        lines += [
            f"**API:** {title} v{version}",
            f"**Paths:** {path_count}",
            "",
        ]

        errors = [i for i in issues if i.severity == "ERROR"]
        warns = [i for i in issues if i.severity == "WARN"]
        infos = [i for i in issues if i.severity == "INFO"]

        if errors:
            lines += ["## Errors (block export)", ""]
            for i in errors:
                lines += [f"- **[{i.gate}]** `{i.path}`: {i.message}", f"  > Fix: {i.suggestion}", ""]

        if warns:
            lines += ["## Warnings", ""]
            for i in warns:
                lines += [f"- **[{i.gate}]** `{i.path}`: {i.message}", f"  > Fix: {i.suggestion}", ""]

        if infos:
            lines += ["## Info", ""]
            for i in infos:
                lines += [f"- `{i.path}`: {i.message}"]

        if not issues:
            lines += ["## All gates passed — spec is ready for use."]

        return "\n".join(lines)

    # ── LLM Explanation Generation ───────────────────────────────────────────────────

    async def _enrich_issues_with_explanations(self, spec: dict, issues: list[ValidationIssue]):
        """Use LLM to generate detailed explanations and fix examples for issues."""
        if not issues:
            return

        # Build issues summary for LLM
        issues_summary = "\n".join(
            f"- [{i.severity}] {i.gate}: {i.message} at {i.path}"
            for i in issues[:10]  # Limit to first 10 issues to avoid token overflow
        )

        # Get relevant spec excerpt (first few paths)
        spec_excerpt = self._get_spec_excerpt(spec, max_paths=3)

        user_msg = f"Issues:\n{issues_summary}\n\nSpec excerpt:\n{spec_excerpt}"

        try:
            explanation = await self._get_llm().complete(
                system=VALIDATION_EXPLANATION_PROMPT,
                user=user_msg,
                task="validation_explanation",
                max_tokens=2000,
            )
            self._parse_and_apply_explanations(issues, explanation)
        except Exception as e:
            logger.warning("Failed to generate LLM explanations: %s", e)

    def _get_spec_excerpt(self, spec: dict, max_paths: int = 3) -> str:
        """Extract a small excerpt of the spec for LLM context."""
        import yaml as pyyaml
        paths = spec.get("paths", {})
        excerpt = {"openapi": spec.get("openapi"), "info": spec.get("info"), "paths": {}}

        for i, (path, path_item) in enumerate(list(paths.items())[:max_paths]):
            if isinstance(path_item, dict):
                excerpt["paths"][path] = {
                    k: v for k, v in path_item.items()
                    if not k.startswith("x-") and isinstance(v, dict)
                }

        return pyyaml.dump(excerpt, sort_keys=False, allow_unicode=True)

    def _parse_and_apply_explanations(self, issues: list[ValidationIssue], explanation: str):
        """Parse LLM response and apply explanations to issues."""
        import json
        import re

        # Try JSON array parsing first
        explanation = explanation.strip()
        if explanation.startswith("```"):
            explanation = self._strip_json_fences(explanation)

        try:
            parsed = json.loads(explanation)
            if isinstance(parsed, list):
                for i, issue in enumerate(issues[:len(parsed)]):
                    if i < len(parsed):
                        item = parsed[i]
                        if isinstance(item, dict):
                            issue.suggestion = item.get("yaml_fix", issue.suggestion)
                            # Add explanation to message if not already present
                            explanation_text = item.get("explanation", "")
                            if explanation_text and not issue.message.endswith(explanation_text[:50]):
                                issue.message = f"{issue.message}\n\nDetails: {explanation_text}"
        except json.JSONDecodeError:
            # Fallback: try to extract suggestions with regex
            for issue in issues:
                match = re.search(rf"{issue.gate}.*?fix.*?:.*?```yaml(.*?)```", explanation, re.IGNORECASE | re.DOTALL)
                if match:
                    issue.suggestion = f"Use this YAML pattern:\n{match.group(1).strip()}"

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        """Strip markdown code fences from JSON response."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            start, end = 1, len(lines)
            for i in range(1, len(lines)):
                if lines[i].startswith("```"):
                    start = i + 1
                    break
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            text = "\n".join(lines[start:end])
        return text
