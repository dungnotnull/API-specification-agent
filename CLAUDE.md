# speckit-enhanced — AI-Powered API Spec Design Agent

**Tagline:** Describe an API in plain English → get a production-ready OpenAPI 3.0 spec, validated, with test stubs — in seconds.

**Current Build Phase:** Phase 1 — Core Agent Modules

---

## Problem Statement

API specification design is a high-friction, error-prone bottleneck in the software development lifecycle. Engineers either write OpenAPI YAML by hand (tedious, incomplete) or generate it post-hoc from code (missing intent). Spec Kit provides a baseline specification management toolchain; this agent enhances it with an LLM-powered intelligence layer that: (1) accepts natural language endpoint descriptions and produces valid OpenAPI 3.0 YAML, (2) validates existing specs for completeness and API design best practices, (3) auto-generates pytest/Jest test stubs with edge cases directly from the spec, (4) advises on protocol choice (REST vs GraphQL vs AsyncAPI) based on use-case semantics, and (5) reverse-engineers OpenAPI specs from existing code using CodeT5+. The agent self-learns daily from ArXiv cs.SE, API design literature, and OpenAPI ecosystem changelogs so its output quality improves over time.

---

## Agent Architecture

```
User Input (NL description / code / existing spec file)
          ↓
┌────────────────────────────────────────────────────────┐
│  SpecKitOrchestrator (agent/orchestrator.py)           │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────┐ │
│  │  Planner   │→ │  Executor  │→ │ Memory / Context │ │
│  └────────────┘  └────────────┘  └──────────────────┘ │
│        ↕               ↕                              │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Modules (agent/modules/)                         │ │
│  │  nl_spec_generator.py   — NL → OpenAPI 3.0 YAML  │ │
│  │  spec_validator.py      — completeness checker   │ │
│  │  test_stub_generator.py — spec → pytest/Jest     │ │
│  │  pattern_advisor.py     — REST/GraphQL/AsyncAPI  │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
          ↓              ↓              ↓
     LLM API        HuggingFace    OpenAPI tooling
   (llm_client)   (CodeT5+/BGE)  (pyyaml/jsonschema)
          ↓
   Generated Spec / Validation Report / Test Stubs
```

**E2E Workflow (10 steps):**
1. User provides NL description / code file / existing spec + workflow type
2. Orchestrator routes to appropriate module(s)
3. `nl_spec_generator` → LLM prompts + CodeT5+ code analysis → draft OpenAPI YAML
4. `spec_validator` → 7-gate completeness check → issue list with severity
5. LLM regenerates/patches spec to satisfy failed gates
6. `test_stub_generator` → parse validated spec → pytest + Jest stubs per endpoint
7. `pattern_advisor` → LLM + semantic analysis → REST/GraphQL/AsyncAPI recommendation
8. Memory manager persists spec, validation results, test stubs
9. Knowledge updater checks for new API design papers daily
10. Final output: spec YAML + validation report + test stubs + pattern advisory Markdown

---

## Module List (`agent/modules/`)

| File | Description |
|------|-------------|
| `nl_spec_generator.py` | Natural language → OpenAPI 3.0 YAML via LLM; code → spec via CodeT5+ reverse engineering |
| `spec_validator.py` | 7-gate completeness validator: status codes, error schemas, auth, descriptions, examples, versioning, security |
| `test_stub_generator.py` | OpenAPI spec → pytest (Python) and Jest (JS) test stubs with happy path + edge case templates |
| `pattern_advisor.py` | Analyzes use-case semantics and recommends REST vs GraphQL vs AsyncAPI with trade-off rationale |

---

## Tools Used (`agent/tools/` / accessed by modules)

| File | Description |
|------|-------------|
| `pyyaml` | Parse and emit OpenAPI YAML |
| `jsonschema` | Validate OpenAPI 3.0 schema structure |
| `openapi-spec-validator` | Full OpenAPI 3.0/3.1 spec conformance check |

---

## HuggingFace Models

| Model ID | Task | Why chosen |
|----------|------|-----------|
| `Salesforce/codet5p-770m` | Code → spec reverse engineering; code understanding | SOTA code generation/understanding; code↔text, no training needed |
| `BAAI/bge-large-en-v1.5` | Semantic similarity for similar spec patterns retrieval | #1 MTEB English retrieval as of 2024; 1024-dim dense embeddings |
| `sentence-transformers/all-MiniLM-L6-v2` | Fast pattern matching; intent classification | 6× faster than bge-large; sufficient for pattern advisor routing |
| `BAAI/bge-reranker-large` | Reranking retrieved spec examples for context injection | Cross-encoder precision boost; best reranking model on BEIR |

---

## LLM API Integration

| Provider | Priority | Use cases |
|----------|----------|-----------|
| Claude (`claude-opus-4-8`) | Primary | NL→spec generation, spec validation explanations, test stub generation, pattern advisor rationale |
| OpenAI (`gpt-4o`) | Fallback | Multimodal (diagram → spec), structured JSON function calling |
| Ollama (`llama3`) | Offline | Privacy-sensitive internal API docs; high-volume batch spec generation |

**Key prompt templates:**
- `NL_TO_SPEC_PROMPT`: System prompt + NL description + few-shot OpenAPI examples → YAML output
- `SPEC_VALIDATION_PROMPT`: Spec YAML + validation checklist → JSON issue list
- `TEST_STUB_PROMPT`: Spec YAML + framework choice → pytest/Jest stubs
- `PATTERN_ADVISOR_PROMPT`: Use-case description + constraint list → protocol recommendation + rationale

---

## Knowledge Crawl Sources

| Source | Categories / Queries | Schedule |
|--------|---------------------|----------|
| ArXiv | cs.SE (software engineering, API design) | Weekly Sunday 02:00 |
| Semantic Scholar | "OpenAPI specification", "API design REST GraphQL", "test generation from spec" | Weekly |
| GitHub Releases | OAI/OpenAPI-Specification, swagger-api/swagger-codegen, APIDevTools/openapi-typescript | Weekly |
| OpenAPI Initiative Blog | openapis.org news | Weekly |

---

## Supporting Tools (`tools/`)

| File | Description |
|------|-------------|
| `tools/knowledge_updater.py` | Crawls ArXiv cs.SE + Semantic Scholar + GitHub releases → appends to SECOND-KNOWLEDGE-BRAIN.md |
| `tools/llm_client.py` | Unified Claude / OpenAI / Ollama client with streaming, retry, and cost tracking |
| `tools/hf_model_manager.py` | Lazy-loading registry for CodeT5+, BGE-large, MiniLM, BGE-reranker with CUDA auto-detect |

---

## Active Development Tasks

- [x] CLAUDE.md — agent identity and architecture
- [x] PROJECT-detail.md — full technical specification
- [x] PROJECT-DEVELOPMENT-PHASE-TRACKING.md — build roadmap
- [x] SECOND-KNOWLEDGE-BRAIN.md — domain knowledge base
- [x] agent/main.py — CLI + FastAPI entry point
- [x] agent/orchestrator.py — core decision loop
- [x] agent/modules/nl_spec_generator.py — NL → OpenAPI + code reverse
- [x] agent/modules/spec_validator.py — completeness validator
- [x] agent/modules/test_stub_generator.py — test stub generator
- [x] agent/modules/pattern_advisor.py — protocol advisor
- [x] agent/memory/memory_manager.py — SQLite persistence
- [x] tools/knowledge_updater.py — research paper crawler
- [x] tools/llm_client.py — unified LLM client
- [x] tools/hf_model_manager.py — HuggingFace model manager
- [x] config/agent_config.yaml — runtime configuration
- [x] config/.env.example — environment variable template
- [x] docker/docker-compose.yml — containerized deployment
- [x] docker/Dockerfile — container image
- [x] tests/test-scenarios.md — 8 test scenarios
- [x] tests/test_agent.py — automated test suite
- [x] requirements.txt — pinned dependencies
- [x] upstream/README.md — Spec Kit fork documentation
- [x] ai_layer/patches/speckit_ai_integration.md — integration guide
