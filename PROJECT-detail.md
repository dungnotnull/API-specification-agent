# speckit-enhanced — Full Technical Specification

## Executive Summary

speckit-enhanced forks the Spec Kit OSS project and adds a four-module AI intelligence layer that transforms how development teams design, validate, and test APIs. The agent accepts natural-language endpoint descriptions and produces production-ready OpenAPI 3.0 YAML, validates existing specs for completeness using a 7-gate checklist, auto-generates pytest/Jest test stubs with edge cases, and advises on protocol selection (REST vs GraphQL vs AsyncAPI). A CodeT5+ reverse-engineering pipeline extracts specs from existing code. Daily self-learning via ArXiv cs.SE ensures the agent's recommendations stay current with API design research.

---

## Problem Statement

Engineering teams spend significant time on manual OpenAPI YAML authoring, catching missing status codes, error schemas, and authentication documentation in code review, and writing boilerplate test files from specs. Spec Kit provides a solid CLI foundation; this agent makes it intelligent and self-improving.

---

## Target Users & Use Cases

| User | Trigger | Agent Output |
|------|---------|-------------|
| Backend engineer | "I need a CRUD endpoint for user profiles with JWT auth" | Complete OpenAPI 3.0 YAML with all status codes + auth scheme |
| API reviewer | Upload existing spec YAML | Validation report: missing error schemas, incomplete descriptions, no security scheme |
| QA engineer | "Generate tests for my user profile spec" | pytest + Jest stubs for happy path, 401, 404, 422, 500 |
| Architect | "We need real-time notifications and complex queries" | Pattern advisory: GraphQL + WebSocket subscriptions with rationale |
| Maintenance engineer | Upload legacy Flask/Express codebase | Auto-generated OpenAPI spec from code analysis |

---

## Agent Architecture

```
User Input
    │
    ├── NL description ──────────────────────────► nl_spec_generator
    │                                                      │
    ├── Existing spec YAML ──────────────────────► spec_validator
    │                                                      │
    ├── Code file(s) ───────────────────────────► nl_spec_generator (reverse)
    │                                                      │
    └── Use-case description ─────────────────► pattern_advisor
                                                           │
                              ┌────────────────────────────▼
                              │   SpecKitOrchestrator       │
                              │   (orchestrator.py)         │
                              └────────┬───────────────────┘
                                       │
              ┌────────────────────────┼──────────────────────┐
              ▼                        ▼                       ▼
     nl_spec_generator.py    spec_validator.py    test_stub_generator.py
              │                        │                       │
              ▼                        ▼                       ▼
         LLM API               jsonschema +              LLM API
       + CodeT5+              openapi-spec-validator    + Jinja2 templates
              │
              ▼
         pyyaml output
              │
              ▼
     ┌─────────────────┐
     │  Memory Manager  │
     │  (SQLite)        │
     └────────┬─────────┘
              │
              ▼
     SECOND-KNOWLEDGE-BRAIN.md
     (daily self-update via knowledge_updater.py)
```

---

## Full Module Catalog

### 1. `nl_spec_generator.py`
**Responsibility:** Convert natural-language API descriptions OR code files into valid OpenAPI 3.0 YAML.

**Inputs:**
- `description: str` — NL endpoint description OR
- `code: str` — source code (Python/JS/Go) for reverse engineering
- `context: dict` — optional: existing schemas, auth requirements, API base URL

**Outputs:**
- `spec: dict` — OpenAPI 3.0 object
- `spec_yaml: str` — serialized YAML
- `confidence: float` — 0.0–1.0 generation confidence
- `warnings: list[str]` — assumptions made by LLM

**Tools called:** `llm_client.complete()`, `hf_model_manager.analyze_code()` (CodeT5+), `pyyaml.safe_load()`

**Quality gate:** jsonschema validate against OpenAPI 3.0 schema; retry up to 3× if invalid

---

### 2. `spec_validator.py`
**Responsibility:** Run 7-gate completeness and best-practice check on any OpenAPI 3.0/3.1 spec.

**Inputs:**
- `spec: dict | str` — parsed spec object or YAML string

**Outputs:**
- `issues: list[ValidationIssue]` — each has: gate, severity (ERROR/WARN/INFO), path, message, suggestion
- `score: float` — 0.0–1.0 completeness score
- `report_md: str` — Markdown-formatted validation report

**7 Validation Gates:**
1. STATUS_CODES — all endpoints declare at least 2xx + 4xx responses
2. ERROR_SCHEMAS — all error responses reference a defined error schema
3. AUTH_COVERAGE — global or per-operation security scheme declared
4. DESCRIPTIONS — all paths/operations/parameters have non-empty description
5. EXAMPLES — at least one request/response example per operation
6. VERSIONING — API version declared in `info.version` and base path
7. SECURITY_SCHEMES — security scheme definitions match declared usage

**Tools called:** `openapi_spec_validator`, `jsonschema`, `llm_client.complete()` (explanation generation)

**Quality gate:** ERROR-severity issues block spec export; WARN-severity included in report

---

### 3. `test_stub_generator.py`
**Responsibility:** Parse a validated OpenAPI spec and generate pytest (Python) and/or Jest (JavaScript) test stubs with happy path + edge case templates.

**Inputs:**
- `spec: dict` — validated OpenAPI 3.0 object
- `framework: str` — "pytest" | "jest" | "both"
- `base_url: str` — server base URL (default from spec servers[0])

**Outputs:**
- `pytest_stubs: str` — Python test file content
- `jest_stubs: str` — JavaScript test file content
- `test_count: int` — total stubs generated

**Test coverage per operation:**
- Happy path (200/201): valid request body + expected response schema assertion
- Not found (404): invalid ID / missing resource
- Validation error (422/400): malformed request body
- Unauthorized (401): missing or invalid auth token
- Server error (500): mock server failure

**Tools called:** `jinja2.Template`, `llm_client.complete()` (edge case expansion), `pyyaml`

**Quality gate:** generated files must be syntactically valid Python/JS (ast.parse / acorn-check)

---

### 4. `pattern_advisor.py`
**Responsibility:** Analyze a use-case description and recommend REST, GraphQL, or AsyncAPI with confidence scores and trade-off rationale.

**Inputs:**
- `use_case: str` — natural language description of what the API needs to do
- `constraints: dict` — optional: latency SLA, team expertise, existing infrastructure

**Outputs:**
- `recommendation: str` — "REST" | "GraphQL" | "AsyncAPI" | "REST+AsyncAPI"
- `confidence: float` — 0.0–1.0
- `rationale: str` — multi-paragraph LLM-generated explanation
- `trade_offs: dict` — for each alternative: pros/cons vs recommended
- `starter_spec: str` — minimal spec snippet in the recommended protocol

**Decision signals:**
- Real-time / event-driven → AsyncAPI
- Complex nested queries / partial field selection → GraphQL
- CRUD / resource-oriented / public API → REST
- Mixed (CRUD + real-time notifications) → REST + AsyncAPI

**Tools called:** `hf_model_manager.encode()` (MiniLM intent classification), `llm_client.complete()`, `FAISS` (similar past recommendations retrieval)

---

## HuggingFace Model Selection

| Model | Task | MTEB/Benchmark Score | Chosen Over |
|-------|------|---------------------|-------------|
| `Salesforce/codet5p-770m` | Code understanding, code→text | HumanEval pass@1 = 0.311 (770M size) | CodeBERT (older, no generation); StarCoder (4B+ too large) |
| `BAAI/bge-large-en-v1.5` | Dense embedding for spec retrieval | MTEB Avg 64.23 (#1 at release) | OpenAI ada-002 (API cost); MiniLM (lower accuracy) |
| `sentence-transformers/all-MiniLM-L6-v2` | Fast intent routing, pattern matching | MTEB Avg 56.26 | bge-large (6× slower for real-time routing) |
| `BAAI/bge-reranker-large` | Cross-encoder reranking of retrieved examples | BEIR nDCG@10 = 0.593 | mono-T5 (slower); RoBERTa cross-encoder (lower BEIR) |

---

## LLM API Integration Spec

### NL → Spec Generation

```
System: You are an expert API designer. Given a natural language endpoint description,
generate a complete, valid OpenAPI 3.0 YAML specification. Include: all likely status codes
(200/201/400/401/403/404/422/500), proper error response schemas, authentication requirements,
parameter descriptions, and at least one example per endpoint. Output ONLY valid YAML.

User: {{nl_description}}
Context schemas: {{existing_schemas_json}}
```

**Token budget:** 2,000 input + 3,000 output (claude-opus-4-8)
**Fallback:** gpt-4o with structured output mode (enforces YAML schema)

### Spec Validation Explanation

```
System: You are an OpenAPI spec reviewer. Given a list of validation issues, explain each one
clearly and provide a concrete fix example in YAML.

User: Issues found: {{issue_list_json}}
Spec excerpt: {{failing_path_yaml}}
```

**Token budget:** 1,500 input + 1,000 output

### Test Stub Generation

```
System: You are a test engineer. Given an OpenAPI 3.0 spec, generate comprehensive {{framework}}
test stubs. Cover: happy path, 4xx errors, validation failures, auth failures.
Use {{framework}} conventions: {{pytest_imports | jest_imports}}.

User: Spec: {{spec_yaml}}
```

**Token budget:** 3,000 input + 4,000 output

### Pattern Advisor

```
System: You are a senior API architect. Analyze the use case and recommend REST, GraphQL,
or AsyncAPI (or a combination). Explain your reasoning with reference to CAP theorem,
query patterns, real-time requirements, and team expertise. Provide a minimal starter spec snippet.

User: Use case: {{use_case}}
Constraints: {{constraints_json}}
```

**Token budget:** 800 input + 1,200 output

---

## E2E Execution Flow

```
Step 1: User calls CLI: `speckit generate --description "User profile CRUD with JWT" --output user_profile.yaml`
Step 2: Orchestrator parses intent → routes to nl_spec_generator
Step 3: nl_spec_generator.generate_from_nl(description) → LLM call (NL_TO_SPEC_PROMPT)
Step 4: LLM returns draft YAML → pyyaml.safe_load() → validate schema
Step 5: If schema invalid → retry with error feedback (max 3 attempts)
Step 6: spec_validator.validate(spec) → run 7 gates → issue_list
Step 7: If ERROR issues → LLM patch_spec(spec, issues) → re-validate
Step 8: test_stub_generator.generate(spec, framework="both") → pytest + Jest stubs
Step 9: memory_manager.save_spec(spec, validation_results, test_stubs)
Step 10: Output: user_profile.yaml + validation_report.md + tests/test_user_profile.py + tests/user_profile.test.js
```

**Error handling:**
- LLM API unavailable → Ollama fallback → template-based spec with placeholders
- CodeT5+ unavailable → simple regex-based code parser fallback
- jsonschema validation failure after 3 retries → return best-effort spec with ERROR flag

---

## `SECOND-KNOWLEDGE-BRAIN.md` Integration

- **Sources:** ArXiv cs.SE + Semantic Scholar "OpenAPI", "REST design", "GraphQL vs REST", "API testing"
- **Crawl config:** weekly Sunday 02:00; daily for OpenAPI spec changelog
- **Dedup strategy:** SHA256 hash of DOI/URL; skip if already in `knowledge_hashes` table
- **Usage:** Pattern advisor retrieves similar past decisions; validator uses latest best practices

---

## `knowledge_updater.py` Spec

- **Inputs:** ArXiv cs.SE categories; Semantic Scholar "API design" queries; GitHub releases for OAI/OpenAPI-Specification
- **Outputs:** Appends new entries to SECOND-KNOWLEDGE-BRAIN.md knowledge log
- **Schedule:** APScheduler CronTrigger weekly Sunday 02:00
- **Failure handling:** Logs error, skips failed source, continues with others; next run retries

---

## `llm_client.py` Spec

- **Providers:** Claude (anthropic SDK) → OpenAI (openai SDK) → Ollama (aiohttp)
- **Retry logic:** Exponential backoff 1s/2s/4s on rate limit or network error
- **Streaming:** Async generator for real-time spec generation display
- **Cost tracking:** Log per-call token counts and USD cost to memory_manager

---

## `hf_model_manager.py` Spec

- **Models:** CodeT5+ (transformers pipeline), BGE-large (SentenceTransformer), MiniLM (SentenceTransformer), BGE-reranker (CrossEncoder)
- **Lazy loading:** Download on first use; cache in `./models/`
- **Idle unload:** 600s inactivity timer; free GPU/CPU memory
- **CUDA:** Auto-detect; fall back to CPU if no GPU

---

## `docker-compose.yml` Spec

**Services:**
- `speckit-agent` — Python 3.12; exposes port 8020; mounts `./data` for SQLite + `./models` for HF cache
- `ollama` — GPU profile; `llama3` pre-pulled; exposes port 11434

**Volumes:** `speckit_data`, `speckit_models`, `ollama_models`

---

## Quality Gates

1. Generated OpenAPI spec must pass `openapi-spec-validator` (0 schema errors)
2. All spec paths must have ≥ 1 success (2xx) + ≥ 1 client error (4xx) response
3. All error responses must reference a reusable `#/components/schemas/Error` schema
4. Global or per-operation `security` field must be present
5. Generated pytest stubs must pass `python -m ast` syntax check
6. Generated Jest stubs must contain valid ES6 (no syntax errors detected by heuristic check)
7. LLM generation confidence score ≥ 0.70 (else flag for human review)

---

## Test Scenarios

See `tests/test-scenarios.md` for 8 end-to-end scenarios with expected outputs.

---

## Key Design Decisions

1. **OpenAPI 3.0 as primary target** — widest toolchain support (Postman, Swagger UI, code generators); 3.1 is opt-in via config flag
2. **CodeT5+ for reverse engineering** — code↔text bidirectional, 770M parameters fits on consumer GPU, no API cost
3. **7-gate validator over single score** — actionable per-gate issues let developers fix incrementally, not just "score 0.6"
4. **Sidecar pattern** — zero modifications to Spec Kit upstream Go code; AI layer is a Python FastAPI sidecar
5. **FAISS for example retrieval** — BGE-large embeddings of past specs enable few-shot examples for generation quality
6. **Both pytest + Jest stubs** — projects rarely use a single language; generating both doubles the utility per spec
7. **Pattern advisor includes starter spec** — reduces friction from "which protocol" to immediate usable scaffold
