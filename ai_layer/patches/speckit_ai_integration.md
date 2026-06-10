# speckit-enhanced AI Integration Guide

## Overview

speckit-enhanced adds a Python FastAPI AI sidecar to the Spec Kit toolchain. The sidecar exposes 7 REST endpoints that transform natural language and code into validated OpenAPI specs, generate test stubs, and advise on API protocol selection.

---

## Architecture

```
User
 │
 ├── CLI: python -m agent.main generate --description "..."
 │           └──► SpecKitOrchestrator
 │                       │
 │         ┌─────────────┼──────────────────┐
 │         ▼             ▼                  ▼
 │  nl_spec_generator  spec_validator  test_stub_generator
 │         │             │                  │
 │         └──── LLM API (Claude/GPT/Ollama) ──────┘
 │                       │
 │         ┌─────────────▼────────────┐
 │         │  HuggingFace Models      │
 │         │  CodeT5+ / BGE / MiniLM  │
 │         └──────────────────────────┘
 │
 └── REST API: POST /api/v1/generate
```

---

## Quickstart

```bash
# Clone and install
cd D:\Dungchan\agent\20
pip install -r requirements.txt

# Set API keys
cp config/.env.example .env
# Edit .env: set ANTHROPIC_API_KEY

# Start server
python -m agent.main serve

# Or with Docker
cd docker
docker-compose up -d
```

---

## REST API Quick Reference

### Generate OpenAPI Spec from NL
```bash
curl -X POST http://localhost:8020/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{
    "description": "CRUD user management API with JWT auth. Users have name, email, role.",
    "base_url": "https://api.myapp.com/v1",
    "api_version": "1.0.0"
  }'
```

**Response:**
```json
{
  "spec_yaml": "openapi: 3.0.3\n...",
  "confidence": 0.92,
  "warnings": [],
  "validation_score": 0.86,
  "validation_issues": []
}
```

### Validate an Existing Spec
```bash
curl -X POST http://localhost:8020/api/v1/validate \
  -H "Content-Type: application/json" \
  -d '{"spec_yaml": "openapi: 3.0.3\n..."}'
```

**Response:**
```json
{
  "score": 0.71,
  "issues": [
    {"gate": "EXAMPLES", "severity": "WARN", "path": "paths./users.get", "message": "...", "suggestion": "..."}
  ],
  "report_md": "# OpenAPI Spec Validation Report\n...",
  "passed_gates": ["STATUS_CODES", "ERROR_SCHEMAS", "AUTH_COVERAGE", "VERSIONING", "SECURITY_SCHEMES"],
  "failed_gates": ["DESCRIPTIONS", "EXAMPLES"]
}
```

### Generate Test Stubs
```bash
curl -X POST http://localhost:8020/api/v1/test-stubs \
  -H "Content-Type: application/json" \
  -d '{"spec_yaml": "...", "framework": "both"}'
```

### Pattern Advisory
```bash
curl -X POST http://localhost:8020/api/v1/advise \
  -H "Content-Type: application/json" \
  -d '{"use_case": "Real-time IoT sensor telemetry with historical queries"}'
```

### Reverse Engineer Spec from Code
```bash
curl -X POST http://localhost:8020/api/v1/generate-from-code \
  -H "Content-Type: application/json" \
  -d '{"code": "@app.route(\"/users\")...", "language": "python"}'
```

### Health & Metrics
```bash
curl http://localhost:8020/health
curl http://localhost:8020/metrics
curl http://localhost:8020/api/v1/cost
```

---

## CLI Quick Reference

```bash
# Generate spec from description
python -m agent.main generate -d "User auth API with JWT" -o user_auth.yaml

# Generate from code file
python -m agent.main reverse myapp/routes.py -l python -o routes_spec.yaml

# Validate an existing spec
python -m agent.main validate existing_spec.yaml -o validation_report.md

# Generate test stubs
python -m agent.main test-stubs user_auth.yaml -f both -o tests/

# Get protocol advisory
python -m agent.main advise -u "Event-driven order fulfillment pipeline"

# Trigger knowledge update
python -m agent.main update-knowledge

# Show cost report
python -m agent.main cost-report
```

---

## Cross-Agent Integration

### With academic-research-enhanced (Folder 18)
The knowledge updater in speckit-enhanced can be augmented by the research agent:
```python
# academic-research-enhanced crawls ArXiv cs.SE daily
# speckit-enhanced reads SECOND-KNOWLEDGE-BRAIN.md for prompt augmentation

# In pattern_advisor.py: inject latest research context into LLM prompt
with open("SECOND-KNOWLEDGE-BRAIN.md") as f:
    brain = f.read()
system = PATTERN_ADVISOR_PROMPT + f"\n\nLatest research context:\n{brain[:2000]}"
```

### With ai-benchmark-agent (Folder 22)
Route all LLM calls through the benchmark middleware to track per-operation metrics:
```python
# In llm_client.py: log call metadata
await benchmark_client.record(
    model=self.claude_model,
    task=task,
    latency_ms=elapsed,
    input_tokens=in_tok,
    output_tokens=out_tok,
    task_success=True,
)
```

### With turbovec-enhanced (Folder 16)
Use TurboVec for fast similarity search over the spec example library:
```python
# Store 1000+ example specs as embeddings in TurboVec
# Retrieve similar past specs for few-shot prompt injection
similar = await turbovec_client.search(query_embedding, top_k=3)
examples = [s["spec_yaml"] for s in similar]
```

---

## Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `speckit_generate_requests_total` | Counter | Total NL → spec generation requests |
| `speckit_validate_requests_total` | Counter | Total spec validation requests |
| `speckit_test_stub_requests_total` | Counter | Total test stub generation requests |
| `speckit_advisor_requests_total` | Counter | Total pattern advisory requests |
| `speckit_knowledge_updates_total` | Counter | Total knowledge base crawls run |
| `speckit_llm_errors_total` | Counter | Total LLM API errors (all providers) |

---

## Production Hardening Checklist

- [ ] Set `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` as Docker secrets (not env vars)
- [ ] Enable PRIVACY_MODE if generating specs from internal/proprietary code
- [ ] Mount `speckit_data` volume to persistent storage (SQLite database)
- [ ] Mount `speckit_models` volume to persistent storage (HF model cache)
- [ ] Configure reverse proxy (nginx) with TLS termination on port 443
- [ ] Set `LOG_LEVEL=WARNING` in production (reduces I/O)
- [ ] Schedule weekly knowledge update: `cron: "0 2 * * 0"`
- [ ] Monitor `/metrics` endpoint with Prometheus + Grafana
- [ ] Set resource limits: `deploy.resources.limits.memory: 4G` (LLM calls + HF models)
- [ ] Run as non-root user (agentuser, UID 1000) — already set in Dockerfile
