"""speckit-enhanced — CLI entry point and FastAPI server."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import click
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agent.orchestrator import SpecKitOrchestrator

app = FastAPI(
    title="speckit-enhanced API",
    description="AI-powered OpenAPI spec generation, validation, and test stub generation",
    version="1.0.0",
)

_orchestrator: Optional[SpecKitOrchestrator] = None


def get_orchestrator() -> SpecKitOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SpecKitOrchestrator()
    return _orchestrator


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    description: str = Field(..., description="Natural language endpoint description")
    existing_schemas: dict = Field(default_factory=dict, description="Existing OpenAPI component schemas")
    base_url: str = Field(default="https://api.example.com/v1", description="API base URL")
    api_version: str = Field(default="1.0.0", description="API version string")


class GenerateFromCodeRequest(BaseModel):
    code: str = Field(..., description="Source code to reverse-engineer spec from")
    language: str = Field(default="python", description="Code language: python|javascript|go")
    base_url: str = Field(default="https://api.example.com/v1")


class GenerateResponse(BaseModel):
    spec_yaml: str
    confidence: float
    warnings: list[str]
    validation_score: float
    validation_issues: list[dict]


class ValidateRequest(BaseModel):
    spec_yaml: str = Field(..., description="OpenAPI 3.0 YAML string to validate")


class ValidateResponse(BaseModel):
    score: float
    issues: list[dict]
    report_md: str
    passed_gates: list[str]
    failed_gates: list[str]


class TestStubRequest(BaseModel):
    spec_yaml: str = Field(..., description="Validated OpenAPI 3.0 YAML")
    framework: str = Field(default="both", description="pytest | jest | both")
    base_url: Optional[str] = None


class TestStubResponse(BaseModel):
    pytest_stubs: Optional[str]
    jest_stubs: Optional[str]
    test_count: int
    operations_covered: int


class AdvisoryRequest(BaseModel):
    use_case: str = Field(..., description="Natural language API use-case description")
    constraints: dict = Field(default_factory=dict, description="Optional: latency_sla_ms, team_expertise, existing_infra")


class AdvisoryResponse(BaseModel):
    recommendation: str
    confidence: float
    rationale: str
    trade_offs: dict
    starter_spec_snippet: str


class KnowledgeUpdateResponse(BaseModel):
    entries_added: int
    sources_crawled: list[str]
    next_scheduled: str


class CostResponse(BaseModel):
    total_usd: float
    by_provider: dict
    by_operation: dict
    call_count: int


# ── FastAPI Endpoints ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "speckit-enhanced", "version": "1.0.0"}


@app.post("/api/v1/generate", response_model=GenerateResponse)
async def generate_spec(req: GenerateRequest):
    """Generate OpenAPI 3.0 YAML from a natural language description."""
    orch = get_orchestrator()
    result = await orch.generate_from_nl(
        description=req.description,
        existing_schemas=req.existing_schemas,
        base_url=req.base_url,
        api_version=req.api_version,
    )
    return GenerateResponse(**result)


@app.post("/api/v1/generate-from-code", response_model=GenerateResponse)
async def generate_from_code(req: GenerateFromCodeRequest):
    """Reverse-engineer an OpenAPI spec from source code using CodeT5+."""
    orch = get_orchestrator()
    result = await orch.generate_from_code(
        code=req.code,
        language=req.language,
        base_url=req.base_url,
    )
    return GenerateResponse(**result)


@app.post("/api/v1/validate", response_model=ValidateResponse)
async def validate_spec(req: ValidateRequest):
    """Run 7-gate completeness check on an OpenAPI 3.0 spec."""
    orch = get_orchestrator()
    result = await orch.validate_spec(req.spec_yaml)
    return ValidateResponse(**result)


@app.post("/api/v1/test-stubs", response_model=TestStubResponse)
async def generate_test_stubs(req: TestStubRequest):
    """Generate pytest and/or Jest test stubs from a validated OpenAPI spec."""
    orch = get_orchestrator()
    result = await orch.generate_test_stubs(
        spec_yaml=req.spec_yaml,
        framework=req.framework,
        base_url=req.base_url,
    )
    return TestStubResponse(**result)


@app.post("/api/v1/advise", response_model=AdvisoryResponse)
async def pattern_advisory(req: AdvisoryRequest):
    """Recommend REST, GraphQL, or AsyncAPI for a given use case."""
    orch = get_orchestrator()
    result = await orch.advise_pattern(
        use_case=req.use_case,
        constraints=req.constraints,
    )
    return AdvisoryResponse(**result)


@app.post("/api/v1/knowledge/update", response_model=KnowledgeUpdateResponse)
async def update_knowledge():
    """Trigger a manual knowledge base update (crawl ArXiv + Semantic Scholar)."""
    orch = get_orchestrator()
    result = await orch.update_knowledge()
    return KnowledgeUpdateResponse(**result)


@app.get("/api/v1/cost", response_model=CostResponse)
async def cost_report():
    """Return LLM API cost summary."""
    orch = get_orchestrator()
    result = await orch.get_cost_report()
    return CostResponse(**result)


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics in text exposition format."""
    orch = get_orchestrator()
    metrics_text = orch.get_prometheus_metrics()
    return StreamingResponse(
        iter([metrics_text]),
        media_type="text/plain; version=0.0.4",
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """speckit-enhanced — AI-powered API specification agent."""


@cli.command()
@click.option("--description", "-d", required=False, help="NL endpoint description")
@click.option("--description-file", "-f", type=click.Path(exists=True), help="File containing NL description")
@click.option("--output", "-o", default="spec.yaml", help="Output YAML file path")
@click.option("--base-url", default="https://api.example.com/v1", help="API base URL")
@click.option("--version", default="1.0.0", help="API version")
def generate(description, description_file, output, base_url, version):
    """Generate OpenAPI 3.0 YAML from a natural language description."""
    if description_file:
        description = Path(description_file).read_text()
    if not description:
        click.echo("Error: provide --description or --description-file", err=True)
        sys.exit(1)

    orch = SpecKitOrchestrator()
    result = asyncio.run(orch.generate_from_nl(description=description, base_url=base_url, api_version=version))

    Path(output).write_text(result["spec_yaml"])
    click.echo(f"Spec written to: {output}")
    click.echo(f"Confidence: {result['confidence']:.2f}  Validation score: {result['validation_score']:.2f}")
    if result["warnings"]:
        click.echo("Warnings:")
        for w in result["warnings"]:
            click.echo(f"  - {w}")
    if result["validation_issues"]:
        click.echo(f"\nValidation issues: {len(result['validation_issues'])}")
        for issue in result["validation_issues"][:5]:
            click.echo(f"  [{issue.get('severity','?')}] {issue.get('message','')}")


@cli.command()
@click.argument("code_file", type=click.Path(exists=True))
@click.option("--language", "-l", default="python", type=click.Choice(["python", "javascript", "go"]))
@click.option("--output", "-o", default="spec.yaml")
def reverse(code_file, language, output):
    """Reverse-engineer an OpenAPI spec from source code using CodeT5+."""
    code = Path(code_file).read_text()
    orch = SpecKitOrchestrator()
    result = asyncio.run(orch.generate_from_code(code=code, language=language))
    Path(output).write_text(result["spec_yaml"])
    click.echo(f"Spec written to: {output}  (confidence: {result['confidence']:.2f})")


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output Markdown report path")
def validate(spec_file, output):
    """Validate an OpenAPI 3.0 spec against the 7-gate completeness checklist."""
    spec_yaml = Path(spec_file).read_text()
    orch = SpecKitOrchestrator()
    result = asyncio.run(orch.validate_spec(spec_yaml))

    click.echo(f"Completeness score: {result['score']:.2f}")
    click.echo(f"Passed gates: {', '.join(result['passed_gates']) or 'none'}")
    click.echo(f"Failed gates: {', '.join(result['failed_gates']) or 'none'}")
    click.echo(f"Issues found: {len(result['issues'])}")

    if output:
        Path(output).write_text(result["report_md"])
        click.echo(f"Report written to: {output}")
    else:
        click.echo("\n" + result["report_md"])


@cli.command("test-stubs")
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--framework", "-f", default="both", type=click.Choice(["pytest", "jest", "both"]))
@click.option("--output-dir", "-o", default="tests", help="Directory to write test files")
def test_stubs(spec_file, framework, output_dir):
    """Generate pytest/Jest test stubs from an OpenAPI spec."""
    spec_yaml = Path(spec_file).read_text()
    orch = SpecKitOrchestrator()
    result = asyncio.run(orch.generate_test_stubs(spec_yaml=spec_yaml, framework=framework))

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    stem = Path(spec_file).stem
    if result.get("pytest_stubs"):
        p = out / f"test_{stem}.py"
        p.write_text(result["pytest_stubs"])
        click.echo(f"pytest stubs: {p}")
    if result.get("jest_stubs"):
        p = out / f"{stem}.test.js"
        p.write_text(result["jest_stubs"])
        click.echo(f"Jest stubs: {p}")
    click.echo(f"Total stubs: {result['test_count']}  Operations covered: {result['operations_covered']}")


@cli.command()
@click.option("--use-case", "-u", required=False, help="API use-case description")
@click.option("--use-case-file", type=click.Path(exists=True))
@click.option("--constraints", "-c", default="{}", help="JSON constraints dict")
def advise(use_case, use_case_file, constraints):
    """Get a REST / GraphQL / AsyncAPI recommendation for your use case."""
    if use_case_file:
        use_case = Path(use_case_file).read_text()
    if not use_case:
        click.echo("Error: provide --use-case or --use-case-file", err=True)
        sys.exit(1)

    constraints_dict = json.loads(constraints)
    orch = SpecKitOrchestrator()
    result = asyncio.run(orch.advise_pattern(use_case=use_case, constraints=constraints_dict))

    click.echo(f"\nRecommendation: {result['recommendation']}  (confidence: {result['confidence']:.0%})")
    click.echo(f"\nRationale:\n{result['rationale']}")
    click.echo(f"\nStarter spec snippet:\n{result['starter_spec_snippet']}")


@cli.command("update-knowledge")
def update_knowledge_cmd():
    """Trigger a manual knowledge base crawl (ArXiv + Semantic Scholar)."""
    orch = SpecKitOrchestrator()
    result = asyncio.run(orch.update_knowledge())
    click.echo(f"Entries added: {result['entries_added']}")
    click.echo(f"Sources crawled: {', '.join(result['sources_crawled'])}")
    click.echo(f"Next scheduled: {result['next_scheduled']}")


@cli.command("cost-report")
def cost_report_cmd():
    """Show LLM API cost summary."""
    orch = SpecKitOrchestrator()
    result = asyncio.run(orch.get_cost_report())
    click.echo(f"Total cost: ${result['total_usd']:.4f} USD  ({result['call_count']} calls)")
    click.echo("By provider:")
    for provider, usd in result["by_provider"].items():
        click.echo(f"  {provider}: ${usd:.4f}")
    click.echo("By operation:")
    for op, usd in result["by_operation"].items():
        click.echo(f"  {op}: ${usd:.4f}")


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8020, help="Bind port")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
@click.option("--start-scheduler", is_flag=True, help="Start background research scheduler")
def serve(host, port, reload, start_scheduler):
    """Start the FastAPI server."""
    if start_scheduler:
        orch = get_orchestrator()
        orch.start_scheduler()
        click.echo("Background research scheduler started.")
    uvicorn.run("agent.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    cli()
