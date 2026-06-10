# speckit-enhanced — Development Phase Tracking

## Quantified Improvement Targets

| Metric | Spec Kit Baseline | Target | Measurement Method |
|--------|-------------------|--------|--------------------|
| Time to valid OpenAPI spec (NL input) | N/A (manual) | ≤ 30 seconds | CLI wall-clock time |
| Spec completeness score (7-gate) | ~40% (typical manual spec) | ≥ 85% | Automated gate check on 50-spec benchmark |
| Test stub coverage (operations covered) | 0% (manual) | ≥ 90% of operations get stubs | spec endpoint count vs stubs generated |
| Pattern advisor accuracy | N/A | ≥ 80% agreement with senior architect review | 20-case expert evaluation |

---

## Phase 0: Research & Architecture (Week 1–2)
**Goal:** Understand Spec Kit upstream, define AI improvement delta, pin versions

### Tasks
- [x] Fork Spec Kit at latest stable tag; document all existing CLI commands and capabilities
- [x] Run Spec Kit upstream test suite; record baseline pass rate
- [x] Read 10 foundational API design papers (REST, GraphQL, AsyncAPI, OpenAPI spec)
- [x] Define 4 quantified improvement targets (see table above)
- [x] Design module interface contracts (inputs/outputs for all 4 modules)
- [x] Select HuggingFace models from Papers with Code leaderboards

### Deliverables
- [x] `upstream/README.md` — fork documentation and capability comparison
- [x] Module interface design doc (inline in PROJECT-detail.md)

### Success Criteria
- [x] Upstream test suite passes with 0 regressions
- [x] All 4 improvement targets defined with measurement methodology

### Estimated Effort
4 person-days

---

## Phase 1: Core Agent Modules (Week 3–5)
**Goal:** Implement 4 domain modules with LLM + HuggingFace integration

### Tasks
- [x] `nl_spec_generator.py` — NL → OpenAPI YAML via LLM (3-attempt retry loop)
- [x] `nl_spec_generator.py` — code → spec via CodeT5+ (reverse engineering mode)
- [x] `spec_validator.py` — 7-gate validator with jsonschema + openapi-spec-validator
- [x] `spec_validator.py` — LLM explanation generation per issue
- [x] `test_stub_generator.py` — Production-grade pytest template for all HTTP methods
- [x] `test_stub_generator.py` — Production-grade Jest template + edge case expansion via LLM
- [x] `pattern_advisor.py` — MiniLM intent classifier + LLM rationale + FAISS retrieval
- [x] `pattern_advisor.py` — starter spec snippet generation per protocol

### Deliverables
- [x] 4 module files with full implementation
- [x] Manual integration test for each module

### Success Criteria
- [x] `nl_spec_generator` produces valid OpenAPI YAML for 10/10 NL test cases
- [x] `spec_validator` identifies all 7 gate types in a deliberately broken test spec
- [x] `test_stub_generator` produces syntactically valid Python (ast.parse check)
- [x] `pattern_advisor` returns recommendation + rationale for 5 sample use cases

### Estimated Effort
10 person-days

---

## Phase 2: Orchestrator + Quality Gates (Week 6–8)
**Goal:** Wire modules into a coherent decision loop with quality enforcement

### Tasks
- [x] `agent/orchestrator.py` — SpecKitOrchestrator with lazy module init
- [x] Implement 7-gate quality enforcement: ERROR gates block export
- [x] Implement LLM patch loop (validate → patch → re-validate, max 3 rounds)
- [x] `agent/memory/memory_manager.py` — SQLite with 6 tables
- [x] APScheduler weekly research loop integration
- [x] Prometheus metrics counters per operation
- [x] Config file loading system

### Deliverables
- [x] `orchestrator.py` — full orchestration loop
- [x] `memory_manager.py` — SQLite persistence layer
- [x] `agent/config.py` — Configuration management

### Success Criteria
- [x] End-to-end: NL input → valid spec YAML in ≤ 30s (timed on 10 runs)
- [x] Quality gate enforcement: ERROR issues prevent spec file output
- [x] SQLite tables: all 6 created with correct schema on first run

### Estimated Effort
6 person-days

---

## Phase 3: HuggingFace Model Integration (Week 9–10)
**Goal:** Integrate and benchmark CodeT5+, BGE-large, MiniLM, BGE-reranker

### Tasks
- [x] `tools/hf_model_manager.py` — singleton registry, lazy loading, CUDA auto-detect
- [x] Integrate CodeT5+ into `nl_spec_generator` code-reverse mode
- [x] Build FAISS index from 50 example OpenAPI specs for pattern retrieval
- [x] Integrate BGE-large + FAISS into `pattern_advisor` similar-case retrieval
- [x] Integrate BGE-reranker into retrieval pipeline
- [x] Benchmark CodeT5+ code→spec quality vs pure LLM approach
- [x] Idle model unloading (600s timer) + memory cleanup
- [x] MPS (Apple Silicon) support

### Deliverables
- [x] `tools/hf_model_manager.py` — full implementation
- [x] FAISS index building capability

### Success Criteria
- [x] CodeT5+ successfully extracts ≥ 3 route definitions from 5 test Flask/Express files
- [x] BGE-large encodes 50 spec summaries in < 10s on CPU
- [x] Idle unload verified: model freed after 600s inactivity

### Estimated Effort
6 person-days

---

## Phase 4: LLM API Integration (Week 11–12)
**Goal:** Claude/OpenAI/Ollama client with prompt engineering and fallback

### Tasks
- [x] `tools/llm_client.py` — Claude/OpenAI/Ollama with streaming + retry
- [x] Design and test 4 prompt templates (NL-to-spec, validation, test-stub, pattern-advisor)
- [x] Few-shot example selection from FAISS index for NL-to-spec prompt
- [x] Ollama offline mode fallback validation
- [x] Token cost tracking integration with memory_manager
- [x] Prompt template manager system

### Deliverables
- [x] `tools/llm_client.py` — full implementation
- [x] 4 production prompt templates (inline in modules)
- [x] `tools/prompt_templates.py` — Prompt template manager

### Success Criteria
- [x] Claude → OpenAI fallback tested: disable ANTHROPIC_API_KEY, confirm OpenAI used
- [x] Ollama fallback tested: disable both cloud keys, confirm llama3 used
- [x] Cost tracking: `cost-report` CLI command shows per-provider totals

### Estimated Effort
4 person-days

---

## Phase 5: SECOND-KNOWLEDGE-BRAIN Pipeline (Week 13–14)
**Goal:** Implement knowledge crawler and run first crawl

### Tasks
- [x] `tools/knowledge_updater.py` — ArXiv cs.SE + Semantic Scholar + GitHub releases
- [x] SHA256 dedup via memory_manager.is_known_paper()
- [x] Append top-10 scored entries to SECOND-KNOWLEDGE-BRAIN.md per crawl run
- [x] Run first crawl: populate 20+ initial entries
- [x] APScheduler CronTrigger weekly Sunday 02:00 integration
- [x] Improved scoring system for relevance ranking
- [x] Better error handling and rate limiting

### Deliverables
- [x] `tools/knowledge_updater.py` — full implementation
- [x] SECOND-KNOWLEDGE-BRAIN.md with ≥ 20 seeded entries

### Success Criteria
- [x] First crawl run: ≥ 10 new papers appended to knowledge brain
- [x] Dedup check: running twice does not add duplicate entries
- [x] APScheduler: knowledge update fires correctly at scheduled time

### Estimated Effort
4 person-days

---

## Phase 6: Docker + Testing (Week 15–16)
**Goal:** Containerize, implement REST API, run all test scenarios

### Tasks
- [x] `agent/main.py` — Click CLI + FastAPI 9 endpoints
- [x] `docker/Dockerfile` — python:3.12-slim non-root agentuser
- [x] `docker/docker-compose.yml` — speckit-agent + ollama
- [x] `tests/test_agent.py` — 35+ automated tests
- [x] `tests/test-scenarios.md` — 8 end-to-end scenarios
- [x] Run all 8 test scenarios; fix failures
- [x] `requirements.txt` — all deps pinned
- [x] `DEPLOYMENT.md` — Comprehensive deployment guide

### Deliverables
- [x] All deployment files
- [x] Test suite passing ≥ 95% of tests
- [x] Deployment documentation

### Success Criteria
- [x] `docker-compose up` starts successfully with health check passing
- [x] All 8 test scenarios pass (or known-skip with documented reason)
- [x] pytest -v shows ≥ 95% pass rate

### Estimated Effort
6 person-days

---

## Phase 7: Cross-Agent Wiring & Documentation (Week 17–18)
**Goal:** Integrate with other agents where applicable

### Tasks
- [x] Cross-agent integration: academic-research-enhanced (folder 18) for API design papers
- [x] Cross-agent integration: ai-benchmark-agent (folder 22) for LLM call metrics
- [x] `ai_layer/patches/speckit_ai_integration.md` — full integration guide
- [x] `upstream/README.md` — fork documentation + improvement delta table
- [x] `README.md` — Project README with quick start
- [x] `INTEGRATION.md` — Comprehensive integration guide
- [x] `DEPLOYMENT.md` — Deployment documentation

### Deliverables
- [x] `ai_layer/patches/speckit_ai_integration.md`
- [x] `upstream/README.md`
- [x] `README.md`
- [x] `INTEGRATION.md`
- [x] `DEPLOYMENT.md`

### Success Criteria
- [x] Integration guide covers quickstart, REST API reference, cross-agent examples
- [x] upstream/README.md clearly documents the Spec Kit version pinned and delta

### Estimated Effort
3 person-days

---

## Total Estimated Effort: 43 person-days

---

## ✅ Project Status: COMPLETE

All phases (0-7) have been completed with production-grade implementation.

### Completed Deliverables Summary

**Phase 0 (Research & Architecture)**
- ✅ upstream/README.md with Spec Kit fork documentation
- ✅ 4 quantified improvement targets defined
- ✅ Module interface contracts designed

**Phase 1 (Core Agent Modules)**
- ✅ nl_spec_generator.py with NL → OpenAPI and CodeT5+ reverse engineering
- ✅ spec_validator.py with 7-gate validator and LLM explanations
- ✅ test_stub_generator.py with production-grade pytest and Jest templates
- ✅ pattern_advisor.py with FAISS retrieval and LLM rationale

**Phase 2 (Orchestrator + Memory)**
- ✅ orchestrator.py with full decision loop and quality gates
- ✅ memory_manager.py with SQLite persistence (6 tables)
- ✅ Config file loading system (agent/config.py)
- ✅ Prometheus metrics integration

**Phase 3 (HuggingFace Integration)**
- ✅ hf_model_manager.py with CUDA/MPS/CPU detection
- ✅ FAISS index building for pattern retrieval
- ✅ Idle model unloading and memory cleanup

**Phase 4 (LLM Integration)**
- ✅ llm_client.py with Claude/OpenAI/Ollama fallback chain
- ✅ Prompt template manager system
- ✅ Streaming support and retry logic
- ✅ Cost tracking integration

**Phase 5 (Knowledge Pipeline)**
- ✅ knowledge_updater.py with ArXiv/Semantic Scholar/GitHub crawling
- ✅ SHA256 deduplication
- ✅ Improved scoring system
- ✅ APScheduler weekly integration

**Phase 6 (Docker + Testing)**
- ✅ Dockerfile with health checks
- ✅ docker-compose.yml with GPU support
- ✅ DEPLOYMENT.md comprehensive guide
- ✅ All dependencies pinned in requirements.txt

**Phase 7 (Documentation)**
- ✅ README.md with quick start
- ✅ INTEGRATION.md with cross-agent examples
- ✅ DEPLOYMENT.md with production deployment
- ✅ upstream/README.md with fork documentation

### Production-Ready Features

✅ **Code Quality**
- No dummy or placeholder code
- Production-grade error handling
- Comprehensive logging
- Type hints throughout
- Docstrings on all public methods

✅ **Architecture**
- Lazy module initialization
- Config-driven behavior
- Environment variable overrides
- Thread-safe operations
- Memory-efficient model management

✅ **Integration**
- REST API with 9 endpoints
- CLI with 8 commands
- Python SDK for direct imports
- Prometheus metrics
- Webhook support

✅ **Deployment**
- Docker containers (CPU + GPU)
- Docker Compose setup
- Health checks
- Volume persistence
- Nginx reverse proxy config
- Kubernetes manifests

✅ **Documentation**
- Quick start guide
- API reference
- Integration examples
- Deployment guide
- Troubleshooting section

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| LLM generates invalid YAML on complex specs | Medium | High | 3-attempt retry with jsonschema error feedback |
| CodeT5+ accuracy low on compiled/obfuscated code | High | Low | Flag as "low confidence" + pure LLM fallback |
| OpenAPI 3.0 spec evolves | Low | Medium | Pin openapi-spec-validator version; update annually |
| Token costs exceed budget on large specs | Medium | Medium | Truncate spec to 8K tokens; use Ollama for batch |
