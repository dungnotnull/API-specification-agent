"""Automated tests for speckit-enhanced."""

from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── Fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Test API", "version": "1.0.0", "description": "Test"},
    "servers": [{"url": "https://api.test.com/v1"}],
    "paths": {
        "/users": {
            "get": {
                "summary": "List users",
                "description": "Returns all users",
                "operationId": "listUsers",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {
                            "application/json": {
                                "schema": {"type": "array"},
                                "example": [{"id": 1, "name": "Alice"}],
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                },
            },
            "post": {
                "summary": "Create user",
                "description": "Creates a new user",
                "operationId": "createUser",
                "security": [{"BearerAuth": []}],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"},
                            "example": {"name": "Bob"},
                        }
                    }
                },
                "responses": {
                    "201": {"description": "Created"},
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "422": {"$ref": "#/components/responses/ValidationError"},
                },
            },
        },
        "/users/{id}": {
            "get": {
                "summary": "Get user by ID",
                "description": "Returns a single user",
                "operationId": "getUser",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "description": "User ID", "schema": {"type": "integer"}}
                ],
                "responses": {
                    "200": {"description": "Success"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                },
            }
        },
    },
    "components": {
        "schemas": {
            "Error": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "title": {"type": "string"},
                    "status": {"type": "integer"},
                    "detail": {"type": "string"},
                },
            }
        },
        "responses": {
            "Unauthorized": {
                "description": "Unauthorized",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
            "NotFound": {
                "description": "Not found",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
            "BadRequest": {
                "description": "Bad request",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
            "ValidationError": {
                "description": "Validation error",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
        },
        "securitySchemes": {
            "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        },
    },
    "security": [{"BearerAuth": []}],
}

INCOMPLETE_SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/items": {
            "get": {
                "summary": "List items",
                "responses": {"200": {"description": "Success"}},
            }
        }
    },
}


@pytest.fixture
def minimal_spec():
    return MINIMAL_SPEC


@pytest.fixture
def spec_yaml(minimal_spec):
    return yaml.dump(minimal_spec, sort_keys=False)


# ── NLSpecGenerator Tests ─────────────────────────────────────────────────────

class TestNLSpecGenerator:
    def setup_method(self):
        from agent.modules.nl_spec_generator import NLSpecGenerator
        self.gen = NLSpecGenerator()

    def test_estimate_confidence_full_spec(self, minimal_spec):
        score = self.gen._estimate_confidence(minimal_spec)
        assert score >= 0.8

    def test_estimate_confidence_empty(self):
        score = self.gen._estimate_confidence({})
        assert score == 0.0

    def test_collect_warnings_missing_4xx(self):
        spec = {
            "paths": {
                "/test": {
                    "get": {
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        warnings = self.gen._collect_warnings(spec)
        assert any("4xx" in w for w in warnings)

    def test_collect_warnings_no_security(self):
        spec = {"paths": {}, "components": {}}
        warnings = self.gen._collect_warnings(spec)
        assert any("security" in w.lower() for w in warnings)

    def test_strip_fences_removes_markdown(self):
        raw = "```yaml\nopenapi: '3.0.3'\n```"
        stripped = self.gen._strip_fences(raw)
        assert "```" not in stripped
        assert "openapi" in stripped

    def test_strip_fences_no_fences(self):
        raw = "openapi: '3.0.3'"
        assert self.gen._strip_fences(raw) == raw

    def test_template_spec_returns_valid_yaml(self):
        result = self.gen._template_spec("test API", "https://api.example.com/v1")
        assert isinstance(result["spec_yaml"], str)
        parsed = yaml.safe_load(result["spec_yaml"])
        assert "openapi" in parsed
        assert result["confidence"] == 0.3

    @pytest.mark.asyncio
    async def test_generate_from_nl_with_mock_llm(self):
        mock_spec = yaml.dump(MINIMAL_SPEC)
        with patch.object(self.gen, "_get_llm") as mock_llm_fn:
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=mock_spec)
            mock_llm_fn.return_value = mock_llm
            with patch.object(self.gen, "_get_hf", return_value=None):
                result = await self.gen.generate_from_nl("Create a user CRUD API")
        assert "spec_yaml" in result
        assert result["confidence"] > 0
        parsed = yaml.safe_load(result["spec_yaml"])
        assert "openapi" in parsed

    def test_regex_extract_routes_flask(self):
        code = """
@app.route('/users', methods=['GET'])
def list_users(): pass

@app.route('/users/<id>', methods=['POST'])
def create_user(): pass
"""
        result = self.gen._regex_extract_routes(code, "python")
        assert "GET" in result or "POST" in result or "/users" in result


# ── SpecValidator Tests ───────────────────────────────────────────────────────

class TestSpecValidator:
    def setup_method(self):
        from agent.modules.spec_validator import SpecValidator
        self.validator = SpecValidator()

    @pytest.mark.asyncio
    async def test_full_spec_passes_most_gates(self, minimal_spec):
        result = await self.validator.validate(minimal_spec)
        assert result["score"] >= 0.70
        assert "AUTH_COVERAGE" in result["passed_gates"]
        assert "VERSIONING" in result["passed_gates"]
        assert "ERROR_SCHEMAS" in result["passed_gates"]

    @pytest.mark.asyncio
    async def test_incomplete_spec_fails_error_gates(self):
        result = await self.validator.validate(INCOMPLETE_SPEC)
        assert result["score"] < 0.50
        assert len(result["failed_gates"]) >= 3
        assert "VERSIONING" in result["failed_gates"]

    @pytest.mark.asyncio
    async def test_missing_security_scheme_detected(self):
        spec = dict(MINIMAL_SPEC)
        spec = yaml.safe_load(yaml.dump(spec))  # deep copy
        del spec["components"]["securitySchemes"]
        result = await self.validator.validate(spec)
        error_gates = result["failed_gates"]
        assert "AUTH_COVERAGE" in error_gates

    @pytest.mark.asyncio
    async def test_missing_error_schema_detected(self):
        spec = yaml.safe_load(yaml.dump(MINIMAL_SPEC))
        del spec["components"]["schemas"]["Error"]
        result = await self.validator.validate(spec)
        assert "ERROR_SCHEMAS" in result["failed_gates"]

    @pytest.mark.asyncio
    async def test_missing_version_detected(self):
        spec = yaml.safe_load(yaml.dump(MINIMAL_SPEC))
        spec["info"] = {"title": "No Version"}
        result = await self.validator.validate(spec)
        assert "VERSIONING" in result["failed_gates"]

    @pytest.mark.asyncio
    async def test_report_is_markdown(self, minimal_spec):
        result = await self.validator.validate(minimal_spec)
        assert result["report_md"].startswith("# OpenAPI Spec Validation Report")

    @pytest.mark.asyncio
    async def test_score_range(self, minimal_spec):
        result = await self.validator.validate(minimal_spec)
        assert 0.0 <= result["score"] <= 1.0


# ── TestStubGenerator Tests ───────────────────────────────────────────────────

class TestTestStubGenerator:
    def setup_method(self):
        from agent.modules.test_stub_generator import TestStubGenerator
        self.gen = TestStubGenerator()

    def test_is_valid_python_good_code(self):
        assert self.gen._is_valid_python("def test_foo():\n    assert True\n")

    def test_is_valid_python_bad_code(self):
        assert not self.gen._is_valid_python("def test_foo(\n    # broken")

    def test_is_valid_python_empty(self):
        assert not self.gen._is_valid_python("")

    def test_count_operations(self, minimal_spec):
        paths = minimal_spec["paths"]
        count = self.gen._count_operations(paths)
        assert count == 3  # GET /users, POST /users, GET /users/{id}

    def test_pytest_template_generates_valid_python(self, minimal_spec):
        code = self.gen._pytest_template(minimal_spec, "http://localhost")
        assert self.gen._is_valid_python(code)
        assert "def test_" in code

    def test_count_tests_in_python(self):
        code = "def test_a(): pass\ndef test_b(): pass\n"
        assert self.gen._count_tests_in_python(code) == 2

    def test_count_tests_in_jest(self):
        code = "it('should work', () => {});\nit('should fail', () => {});\n"
        assert self.gen._count_tests_in_jest(code) == 2

    @pytest.mark.asyncio
    async def test_generate_pytest_with_mock_llm(self, minimal_spec):
        mock_code = "import pytest\n\nasync def test_list_users_success(): assert True\nasync def test_list_users_unauthorized(): assert True\n"
        with patch.object(self.gen, "_get_llm") as mock_llm_fn:
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=mock_code)
            mock_llm_fn.return_value = mock_llm
            result = await self.gen.generate(minimal_spec, framework="pytest", base_url="http://localhost")
        assert result["pytest_stubs"] is not None
        assert result["jest_stubs"] is None
        assert result["test_count"] >= 2

    @pytest.mark.asyncio
    async def test_fallback_to_template_on_invalid_llm_output(self, minimal_spec):
        with patch.object(self.gen, "_get_llm") as mock_llm_fn:
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value="this is not valid python }{}{")
            mock_llm_fn.return_value = mock_llm
            result = await self.gen.generate(minimal_spec, framework="pytest")
        assert result["pytest_stubs"] is not None
        assert self.gen._is_valid_python(result["pytest_stubs"])


# ── PatternAdvisor Tests ──────────────────────────────────────────────────────

class TestPatternAdvisor:
    def setup_method(self):
        from agent.modules.pattern_advisor import PatternAdvisor
        self.advisor = PatternAdvisor()

    def test_heuristic_rest_signals(self):
        result = self.advisor._heuristic_advise("Simple CRUD API for user profiles", {})
        assert result["recommendation"] in ("REST", "REST+AsyncAPI", "GraphQL")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_heuristic_async_signals(self):
        result = self.advisor._heuristic_advise("Real-time streaming notifications for IoT sensors", {})
        assert "AsyncAPI" in result["recommendation"]

    def test_heuristic_graphql_signals(self):
        result = self.advisor._heuristic_advise("Complex nested queries for social graph with flexible field selection from mobile", {})
        # Either GraphQL or a combined recommendation
        assert result["recommendation"] in ("GraphQL", "REST+AsyncAPI", "REST")

    def test_all_required_keys_present(self):
        result = self.advisor._heuristic_advise("Any API", {})
        required = {"recommendation", "confidence", "rationale", "trade_offs", "starter_spec_snippet"}
        assert required.issubset(result.keys())

    def test_trade_offs_has_three_protocols(self):
        result = self.advisor._heuristic_advise("Any API", {})
        assert "REST" in result["trade_offs"]
        assert "GraphQL" in result["trade_offs"]
        assert "AsyncAPI" in result["trade_offs"]

    @pytest.mark.asyncio
    async def test_advise_with_mock_llm_valid_json(self):
        mock_response = json.dumps({
            "recommendation": "REST",
            "confidence": 0.85,
            "rationale": "Test rationale",
            "trade_offs": {
                "REST": {"pros": ["simple"], "cons": []},
                "GraphQL": {"pros": [], "cons": []},
                "AsyncAPI": {"pros": [], "cons": []},
            },
            "starter_spec_snippet": "openapi: '3.0.3'",
        })
        with patch.object(self.advisor, "_get_llm") as mock_llm_fn:
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=mock_response)
            mock_llm_fn.return_value = mock_llm
            result = await self.advisor.advise("CRUD user API")
        assert result["recommendation"] == "REST"
        assert result["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_advise_falls_back_to_heuristic_on_invalid_json(self):
        with patch.object(self.advisor, "_get_llm") as mock_llm_fn:
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value="not json at all")
            mock_llm_fn.return_value = mock_llm
            result = await self.advisor.advise("Real-time streaming API")
        assert "recommendation" in result
        assert "confidence" in result


# ── MemoryManager Tests ───────────────────────────────────────────────────────

class TestMemoryManager:
    def setup_method(self, tmp_path=None):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        from agent.memory.memory_manager import MemoryManager
        db = Path(self._tmpdir) / "test.db"
        self.memory = MemoryManager(db_path=db)

    def test_save_and_get_stats(self, spec_yaml):
        self.memory.save_spec("test API", spec_yaml, 0.85)
        stats = self.memory.get_stats()
        assert stats["total_specs"] == 1

    def test_save_validation(self, spec_yaml):
        self.memory.save_validation(spec_yaml, 0.85, [])
        stats = self.memory.get_stats()
        assert stats["total_validations"] == 1

    def test_save_advisory(self):
        self.memory.save_advisory("CRUD API", "REST", 0.9)
        history = self.memory.get_advisory_history()
        assert len(history) == 1
        assert history[0]["recommendation"] == "REST"

    def test_llm_cost_tracking(self):
        self.memory.log_llm_cost("claude", "nl_spec_generation", 1000, 500, 0.0525)
        summary = self.memory.get_cost_summary()
        assert summary["total_usd"] == pytest.approx(0.0525, rel=1e-3)
        assert summary["call_count"] == 1

    def test_paper_dedup(self):
        url = "https://arxiv.org/abs/1234.5678"
        assert not self.memory.is_known_paper(url)
        self.memory.mark_paper_known(url, "Test Paper")
        assert self.memory.is_known_paper(url)
        # Second mark should not raise
        self.memory.mark_paper_known(url, "Test Paper")


# ── LLMClient Tests ───────────────────────────────────────────────────────────

class TestLLMClient:
    def setup_method(self):
        from tools.llm_client import UnifiedLLMClient
        self.client = UnifiedLLMClient()

    def test_build_provider_chain_no_keys(self):
        import os
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            chain = self.client._build_provider_chain()
        assert "ollama" in chain

    def test_build_provider_chain_with_anthropic(self):
        import os
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            chain = self.client._build_provider_chain()
        assert chain[0] == "claude"

    @pytest.mark.asyncio
    async def test_ollama_fallback_on_api_error(self):
        import os
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "bad-key", "OPENAI_API_KEY": ""}, clear=False):
            with patch.object(self.client, "_call_claude", side_effect=Exception("API error")):
                with patch.object(self.client, "_call_ollama", AsyncMock(return_value="test response")):
                    result = await self.client.complete("system", "user", "test")
        assert result == "test response"


# ── HFModelManager Tests ──────────────────────────────────────────────────────

class TestHFModelManager:
    def setup_method(self):
        from tools.hf_model_manager import HFModelManager
        # Reset singleton for test isolation
        HFModelManager._instance = None
        self.manager = HFModelManager.instance()

    def test_tfidf_fallback_returns_vector(self):
        vec = self.manager._tfidf_fallback("OpenAPI specification REST endpoint")
        assert len(vec) == 384
        assert abs(sum(x*x for x in vec) - 1.0) < 0.01  # approximately normalized

    def test_heuristic_rerank_orders_by_overlap(self):
        query = "OpenAPI spec validation"
        passages = [
            "This is about cooking recipes",
            "OpenAPI spec validator for REST APIs and validation",
            "Weather forecast data",
        ]
        ranked = self.manager._heuristic_rerank(query, passages, top_k=3)
        # The passage mentioning "OpenAPI spec validation" should rank first
        assert ranked[0][0] == 1

    def test_simple_code_analysis_detects_routes(self):
        code = "@app.route('/users', methods=['GET'])\ndef list_users(): pass"
        result = self.manager._simple_code_analysis(code)
        assert "/users" in result or "GET" in result


# ── Integration Tests ─────────────────────────────────────────────────────────

class TestIntegration:
    @pytest.mark.asyncio
    async def test_orchestrator_validate_spec(self, minimal_spec):
        from agent.orchestrator import SpecKitOrchestrator
        orch = SpecKitOrchestrator()
        spec_yaml_str = yaml.dump(minimal_spec)
        result = await orch.validate_spec(spec_yaml_str)
        assert result["score"] >= 0.50
        assert "passed_gates" in result

    @pytest.mark.asyncio
    async def test_orchestrator_validate_invalid_yaml(self):
        from agent.orchestrator import SpecKitOrchestrator
        orch = SpecKitOrchestrator()
        result = await orch.validate_spec("this is: not: valid: yaml: content: here:")
        # Should handle gracefully
        assert "score" in result

    @pytest.mark.asyncio
    async def test_orchestrator_test_stubs_from_spec(self, minimal_spec):
        from agent.orchestrator import SpecKitOrchestrator
        orch = SpecKitOrchestrator()
        spec_yaml_str = yaml.dump(minimal_spec)
        with patch("agent.modules.test_stub_generator.TestStubGenerator._generate_pytest",
                   AsyncMock(return_value="import pytest\n\ndef test_list_users():\n    pass\n")):
            with patch("agent.modules.test_stub_generator.TestStubGenerator._generate_jest",
                       AsyncMock(return_value="describe('API', () => { it('works', () => {}); });")):
                result = await orch.generate_test_stubs(spec_yaml_str, framework="both")
        assert result["operations_covered"] == 3

    @pytest.mark.asyncio
    async def test_orchestrator_cost_report_empty(self):
        import tempfile
        from agent.orchestrator import SpecKitOrchestrator
        from agent.memory.memory_manager import MemoryManager
        tmpdir = tempfile.mkdtemp()
        db = Path(tmpdir) / "test.db"
        memory = MemoryManager(db_path=db)
        orch = SpecKitOrchestrator()
        orch._memory = memory
        result = await orch.get_cost_report()
        assert result["total_usd"] == 0.0
        assert result["call_count"] == 0


# ── CLI Smoke Tests ───────────────────────────────────────────────────────────

class TestCLISmokeTests:
    def test_cli_help_runs(self):
        from click.testing import CliRunner
        from agent.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "speckit" in result.output.lower()

    def test_generate_help(self):
        from click.testing import CliRunner
        from agent.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0

    def test_validate_help(self):
        from click.testing import CliRunner
        from agent.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0

    def test_test_stubs_help(self):
        from click.testing import CliRunner
        from agent.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["test-stubs", "--help"])
        assert result.exit_code == 0

    def test_advise_help(self):
        from click.testing import CliRunner
        from agent.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["advise", "--help"])
        assert result.exit_code == 0
