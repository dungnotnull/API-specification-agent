"""Prompt template management for speckit-enhanced LLM interactions."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).parent.parent

logger = logging.getLogger(__name__)


# Default system prompts for each task
DEFAULT_PROMPTS = {
    "nl_spec_generation": """You are an expert API designer. Generate a complete, valid OpenAPI 3.0.3 YAML specification from the user's natural language description.

Requirements:
- Include ALL likely status codes: 200/201/400/401/403/404/422/500 (use only applicable ones per endpoint)
- Define a reusable Error schema in components/schemas/Error following RFC 7807 (type, title, status, detail fields)
- Add authentication: JWT Bearer security scheme unless explicitly stated otherwise
- Write non-empty descriptions for every path, operation, and parameter
- Include at least one request body example and one response example per operation
- Use proper HTTP methods: GET for reads, POST for creates, PUT/PATCH for updates, DELETE for deletes
- Set info.title, info.description, info.version
- Set servers[0].url to the provided base URL

Output ONLY valid OpenAPI 3.0.3 YAML. No markdown code fences. No extra explanation.""",

    "code_reverse_spec": """You are an expert API analyst. Analyze the following {language} source code and extract an OpenAPI 3.0.3 specification.

Look for:
- HTTP route decorators/annotations (Flask @app.route, Express router.get, Gin r.GET, etc.)
- Request body schemas (Pydantic models, Joi schemas, Go structs)
- Response schemas and status codes
- Authentication middleware
- Path parameters, query parameters, header parameters

Output ONLY valid OpenAPI 3.0.3 YAML. No markdown. No explanation.""",

    "spec_patch": """You are an OpenAPI expert. The following OpenAPI 3.0 spec has validation errors.
Fix ALL listed issues and return the corrected complete spec.

Issues to fix:
{issues}

Output ONLY the corrected complete OpenAPI 3.0.3 YAML.""",

    "validation_explanation": """You are an OpenAPI spec reviewer. For each validation issue below,
provide a concise explanation (2 sentences max) and a minimal YAML snippet that fixes it.

Return JSON array: [{{"issue_id": "...", "explanation": "...", "yaml_fix": "..."}}]

Issues:
{issues}

Spec excerpt (relevant paths):
{spec_excerpt}""",

    "test_stub_generation_pytest": """You are a test engineer. Generate comprehensive pytest test stubs for the given OpenAPI 3.0 spec.

For each operation include:
1. Happy path test (expected 2xx response, valid request body)
2. Not-found test (404 with invalid ID where applicable)
3. Validation error test (422/400 with malformed request body)
4. Unauthorized test (401 with missing/invalid JWT token)
5. One semantically meaningful edge case

Use httpx AsyncClient or requests. Follow pytest conventions:
- async def test_xxx(): for async
- fixtures: @pytest.fixture for client setup
- assert response.status_code == expected
- assert response.json() structure

Output ONLY valid Python code. No markdown fences. No explanations.""",

    "test_stub_generation_jest": """You are a test engineer. Generate comprehensive Jest + supertest test stubs for the given OpenAPI 3.0 spec.

For each operation include:
1. Happy path test (expected 2xx response)
2. Not-found test (404)
3. Validation error test (422/400)
4. Unauthorized test (401 missing token)
5. One edge case

Use axios or node-fetch. Follow Jest conventions:
- describe('OPERATION', () => {{ it('should ...', ...) }})
- beforeAll / afterAll for server setup
- expect(response.status).toBe(expected)

Output ONLY valid JavaScript/ES6 code. No markdown. No explanations.""",

    "pattern_advisory": """You are a senior API architect. Analyze the use case and recommend the best API protocol.

Protocols to consider:
- REST: best for CRUD, resource-oriented, public APIs, wide toolchain support
- GraphQL: best for complex nested queries, rapid client iteration, mobile with bandwidth constraints, multiple consumers needing different shapes
- AsyncAPI: best for real-time/event-driven, notifications, streaming, IoT, financial ticks
- REST+AsyncAPI: combined when CRUD + real-time notifications both needed

Your response MUST be valid JSON with this exact structure:
{{
  "recommendation": "REST" | "GraphQL" | "AsyncAPI" | "REST+AsyncAPI",
  "confidence": 0.0-1.0,
  "rationale": "3-5 sentence explanation referencing CAP theorem, query patterns, real-time requirements",
  "trade_offs": {{
    "REST": {{"pros": ["..."], "cons": ["..."]}},
    "GraphQL": {{"pros": ["..."], "cons": ["..."]}},
    "AsyncAPI": {{"pros": ["..."], "cons": ["..."]}}
  }},
  "starter_spec_snippet": "minimal YAML spec snippet in the recommended protocol"
}}

Return ONLY the JSON object. No markdown. No explanation outside the JSON.""",
}


class PromptTemplateManager:
    """Manages prompt templates for LLM interactions."""

    def __init__(self):
        self._templates = DEFAULT_PROMPTS.copy()
        self._load_custom_templates()

    def _load_custom_templates(self):
        """Load custom prompt templates from file if available."""
        template_path = ROOT / "config" / "prompt_templates.yaml"
        if not template_path.exists():
            return

        try:
            import yaml
            with open(template_path, "r") as f:
                custom = yaml.safe_load(f) or {}

            for task, prompt in custom.items():
                if isinstance(prompt, str) and prompt.strip():
                    self._templates[task] = prompt
                    logger.debug("Loaded custom prompt template for task: %s", task)

            logger.info("Loaded %d custom prompt templates from %s", len(custom), template_path)
        except Exception as e:
            logger.warning("Failed to load custom prompt templates: %s", e)

    def get_prompt(self, task: str) -> str:
        """Get the prompt template for a specific task."""
        return self._templates.get(task, DEFAULT_PROMPTS.get(task, "You are a helpful assistant."))

    def format_prompt(self, task: str, **kwargs: Any) -> str:
        """Format a prompt template with provided variables."""
        template = self.get_prompt(task)
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning("Missing format variable %s in prompt template %s", e, task)
            return template

    def add_template(self, task: str, template: str):
        """Add or override a prompt template."""
        self._templates[task] = template

    def list_tasks(self) -> list[str]:
        """List all available task names."""
        return list(self._templates.keys())


# Global prompt manager instance
_prompt_manager: PromptTemplateManager = None


def get_prompt_manager() -> PromptTemplateManager:
    """Get the global prompt template manager instance."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptTemplateManager()
    return _prompt_manager
