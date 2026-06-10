"""SpecKitOrchestrator — core agent decision loop for speckit-enhanced."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent

logger = logging.getLogger(__name__)


def get_config():
    """Get the global configuration."""
    from agent.config import get_config
    return get_config()


class SpecKitOrchestrator:
    """
    Orchestrates the four AI modules: nl_spec_generator, spec_validator,
    test_stub_generator, and pattern_advisor.

    Modules are lazily initialized on first use to keep startup fast.
    """

    def __init__(self):
        self._nl_gen = None
        self._validator = None
        self._test_gen = None
        self._advisor = None
        self._memory = None
        self._llm = None
        self._scheduler = None

        # Prometheus-compatible counters
        self._counters: dict[str, int] = {
            "generate_requests_total": 0,
            "validate_requests_total": 0,
            "test_stub_requests_total": 0,
            "advisor_requests_total": 0,
            "knowledge_updates_total": 0,
            "llm_errors_total": 0,
        }

    # ── Lazy module accessors ─────────────────────────────────────────────────

    def _get_nl_gen(self):
        if self._nl_gen is None:
            from agent.modules.nl_spec_generator import NLSpecGenerator
            self._nl_gen = NLSpecGenerator()
        return self._nl_gen

    def _get_validator(self):
        if self._validator is None:
            from agent.modules.spec_validator import SpecValidator
            self._validator = SpecValidator()
        return self._validator

    def _get_test_gen(self):
        if self._test_gen is None:
            from agent.modules.test_stub_generator import TestStubGenerator
            self._test_gen = TestStubGenerator()
        return self._test_gen

    def _get_advisor(self):
        if self._advisor is None:
            from agent.modules.pattern_advisor import PatternAdvisor
            self._advisor = PatternAdvisor()
        return self._advisor

    def _get_memory(self):
        if self._memory is None:
            from agent.memory.memory_manager import MemoryManager
            self._memory = MemoryManager()
        return self._memory

    def _get_llm(self):
        if self._llm is None:
            from tools.llm_client import UnifiedLLMClient
            self._llm = UnifiedLLMClient()
        return self._llm

    # ── Core Operations ───────────────────────────────────────────────────────

    async def generate_from_nl(
        self,
        description: str,
        existing_schemas: dict = None,
        base_url: str = None,
        api_version: str = None,
    ) -> dict:
        """
        Full pipeline: NL description → draft spec → validate → patch if needed.

        Returns dict with: spec_yaml, confidence, warnings, validation_score, validation_issues
        """
        config = get_config()

        # Apply config defaults
        if base_url is None:
            base_url = config.get("spec_generation.default_base_url", "https://api.example.com/v1")
        if api_version is None:
            api_version = config.get("spec_generation.default_api_version", "1.0.0")

        self._counters["generate_requests_total"] += 1
        t0 = time.monotonic()

        try:
            gen = self._get_nl_gen()
            validator = self._get_validator()
            memory = self._get_memory()

            # Step 1: Generate draft spec
            draft = await gen.generate_from_nl(
                description=description,
                existing_schemas=existing_schemas or {},
                base_url=base_url,
                api_version=api_version,
            )

            # Step 2: Validate draft
            val_result = await validator.validate(draft["spec"])

            # Step 3: Patch loop — fix ERROR-severity issues, max 3 rounds
            config = get_config()
            max_attempts = config.get("spec_generation.max_patch_attempts", 3)

            if val_result["failed_error_gates"]:
                for attempt in range(max_attempts):
                    patched = await gen.patch_spec(draft["spec"], val_result["issues"])
                    val_result = await validator.validate(patched["spec"])
                    draft = patched
                    if not val_result["failed_error_gates"]:
                        logger.info("Patch attempt %d: All ERROR gates fixed", attempt + 1)
                        break
                    logger.warning("Patch attempt %d: still %d ERROR gates", attempt + 1, len(val_result["failed_error_gates"]))

                # If still failing after max attempts, apply quality gate
                if val_result["failed_error_gates"] and config.get("quality_gates.require_no_error_gates", True):
                    logger.error("Quality gate failed: %d ERROR gates remain after %d patch attempts",
                               len(val_result["failed_error_gates"]), max_attempts)
                    draft["warnings"].append("Spec has ERROR-severity validation issues that could not be auto-fixed")

            # Step 4: Persist
            memory.save_spec(
                description=description,
                spec_yaml=draft["spec_yaml"],
                validation_score=val_result["score"],
                validation_issues=val_result["issues"],
            )

            elapsed = time.monotonic() - t0
            logger.info("generate_from_nl completed in %.2fs  score=%.2f", elapsed, val_result["score"])

            return {
                "spec_yaml": draft["spec_yaml"],
                "confidence": draft["confidence"],
                "warnings": draft["warnings"],
                "validation_score": val_result["score"],
                "validation_issues": val_result["issues"],
            }

        except Exception as e:
            logger.error("generate_from_nl failed: %s", e, exc_info=True)
            self._counters["llm_errors_total"] += 1
            raise

    async def generate_from_code(
        self,
        code: str,
        language: str = "python",
        base_url: str = "https://api.example.com/v1",
    ) -> dict:
        """
        Reverse-engineer an OpenAPI spec from source code using CodeT5+.

        Returns dict with: spec_yaml, confidence, warnings, validation_score, validation_issues
        """
        self._counters["generate_requests_total"] += 1

        gen = self._get_nl_gen()
        validator = self._get_validator()
        memory = self._get_memory()

        draft = await gen.generate_from_code(code=code, language=language, base_url=base_url)
        val_result = await validator.validate(draft["spec"])

        memory.save_spec(
            description=f"[reverse-engineered from {language} code]",
            spec_yaml=draft["spec_yaml"],
            validation_score=val_result["score"],
            validation_issues=val_result["issues"],
        )

        return {
            "spec_yaml": draft["spec_yaml"],
            "confidence": draft["confidence"],
            "warnings": draft["warnings"],
            "validation_score": val_result["score"],
            "validation_issues": val_result["issues"],
        }

    async def validate_spec(self, spec_yaml: str) -> dict:
        """
        Run 7-gate completeness check on an OpenAPI spec.

        Returns dict with: score, issues, report_md, passed_gates, failed_gates
        """
        self._counters["validate_requests_total"] += 1
        import yaml as pyyaml

        try:
            spec = pyyaml.safe_load(spec_yaml)
        except Exception as e:
            return {
                "score": 0.0,
                "issues": [{"severity": "ERROR", "gate": "PARSE", "message": f"YAML parse error: {e}"}],
                "report_md": f"# Validation Failed\n\nYAML parse error: {e}",
                "passed_gates": [],
                "failed_gates": ["PARSE"],
            }

        validator = self._get_validator()
        result = await validator.validate(spec)

        self._get_memory().save_validation(
            spec_yaml=spec_yaml,
            score=result["score"],
            issues=result["issues"],
        )

        return result

    async def generate_test_stubs(
        self,
        spec_yaml: str,
        framework: str = "both",
        base_url: Optional[str] = None,
    ) -> dict:
        """
        Generate pytest and/or Jest test stubs from a validated OpenAPI spec.

        Returns dict with: pytest_stubs, jest_stubs, test_count, operations_covered
        """
        self._counters["test_stub_requests_total"] += 1
        import yaml as pyyaml

        spec = pyyaml.safe_load(spec_yaml)
        if base_url is None and "servers" in spec:
            servers = spec.get("servers", [])
            base_url = servers[0].get("url", "http://localhost") if servers else "http://localhost"

        test_gen = self._get_test_gen()
        result = await test_gen.generate(spec=spec, framework=framework, base_url=base_url or "http://localhost")

        self._get_memory().save_test_stubs(
            spec_yaml=spec_yaml,
            pytest_stubs=result.get("pytest_stubs"),
            jest_stubs=result.get("jest_stubs"),
            test_count=result["test_count"],
        )

        return result

    async def advise_pattern(self, use_case: str, constraints: dict = None) -> dict:
        """
        Recommend REST, GraphQL, or AsyncAPI for a given use case.

        Returns dict with: recommendation, confidence, rationale, trade_offs, starter_spec_snippet
        """
        self._counters["advisor_requests_total"] += 1
        advisor = self._get_advisor()
        result = await advisor.advise(use_case=use_case, constraints=constraints or {})

        self._get_memory().save_advisory(
            use_case=use_case,
            recommendation=result["recommendation"],
            confidence=result["confidence"],
        )

        return result

    async def update_knowledge(self) -> dict:
        """Trigger a manual knowledge base update."""
        self._counters["knowledge_updates_total"] += 1
        from tools.knowledge_updater import KnowledgeUpdater
        updater = KnowledgeUpdater()
        result = await updater.run_update()
        return result

    async def get_cost_report(self) -> dict:
        """Return LLM API cost summary from memory."""
        memory = self._get_memory()
        return memory.get_cost_summary()

    def get_prometheus_metrics(self) -> str:
        lines = []
        for metric, value in self._counters.items():
            lines.append(f"# HELP speckit_{metric} speckit-enhanced {metric}")
            lines.append(f"# TYPE speckit_{metric} counter")
            lines.append(f"speckit_{metric} {value}")
        return "\n".join(lines) + "\n"

    # ── Scheduler ─────────────────────────────────────────────────────────────

    def start_scheduler(self):
        """Start APScheduler for weekly knowledge updates."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler = BackgroundScheduler()
            self._scheduler.add_job(
                func=lambda: asyncio.run(self.update_knowledge()),
                trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
                id="weekly_knowledge_update",
                replace_existing=True,
            )
            self._scheduler.start()
            logger.info("Scheduler started — weekly knowledge update at Sunday 02:00")
        except ImportError:
            logger.warning("APScheduler not installed; scheduler disabled")
