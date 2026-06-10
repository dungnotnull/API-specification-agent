# SECOND-KNOWLEDGE-BRAIN — speckit-enhanced
## API Spec Design, OpenAPI, REST/GraphQL/AsyncAPI, Test Generation

*Self-updating knowledge base. Updated weekly via `tools/knowledge_updater.py`.*

---

## Core Concepts & Frameworks

### OpenAPI Specification (OAS)
- OpenAPI 3.0 is the de facto standard for RESTful API description (formerly Swagger)
- Key objects: `info`, `paths`, `components` (schemas, responses, parameters, securitySchemes), `security`
- Status codes best practice: always document 2xx success + 4xx client error + 5xx server error
- Error schema best practice: use a reusable `Problem Details` schema (RFC 7807)
- OpenAPI 3.1 aligns with JSON Schema draft 2020-12; backward-incompatible with 3.0 on several keywords

### REST Design Principles
- Richardson Maturity Model (RMM): Level 0 (HTTP tunnel) → Level 1 (Resources) → Level 2 (HTTP verbs) → Level 3 (Hypermedia/HATEOAS)
- HATEOAS: responses include hypermedia links to related resources/actions
- Idempotency: GET/PUT/DELETE are idempotent; POST is not
- Content negotiation: `Accept` and `Content-Type` headers drive representation format

### GraphQL
- Single endpoint (`/graphql`); client specifies exact fields needed → no over/under-fetching
- Schema Definition Language (SDL): `type`, `query`, `mutation`, `subscription`
- N+1 problem: mitigate with DataLoader batching
- Best for: complex nested queries, rapid client-driven iteration, mobile with bandwidth constraints

### AsyncAPI
- Async/event-driven API specification standard (equivalent of OpenAPI for message brokers)
- Supports: WebSockets, AMQP, MQTT, Kafka, SNS/SQS, NATS
- Key objects: `channels`, `messages`, `bindings`, `servers`
- Best for: real-time notifications, event streaming, IoT, financial ticks

### API-First Development
- Write the spec before writing implementation code
- Contract testing: producer and consumer independently test against the shared spec
- Spec versioning: semver in `info.version`; breaking changes increment major version

---

## Key Research Papers

| Title | Authors | Year | Venue | DOI/Link | Key Finding | Relevance |
|-------|---------|------|-------|----------|-------------|-----------|
| "REST: Architectural Styles and the Design of Network-based Software Architectures" | Fielding | 2000 | PhD Dissertation | https://ics.uci.edu/~fielding/pubs/dissertation/top.htm | Defines REST constraints; statelessness, uniform interface, layered system | Foundation for REST API design |
| "GraphQL: A Data Query Language" | Facebook/Meta | 2015 | Open-source spec | https://graphql.org/foundation/ | Type system + runtime for executing queries; solves over/under-fetching | GraphQL pattern advisor |
| "AsyncAPI Specification" | AsyncAPI Initiative | 2016 | Open standard | https://www.asyncapi.com/docs/reference/specification/latest | Event-driven API description analogous to OpenAPI | AsyncAPI pattern advisor |
| "Problem Details for HTTP APIs" (RFC 7807) | Nottingham & Wilde | 2016 | IETF RFC | https://datatracker.ietf.org/doc/html/rfc7807 | Standardized error response format: type/title/status/detail/instance | Error schema validation gate |
| "Evaluating the Consistency of OpenAPI Specifications in Open-Source Projects" | Vaziri et al. | 2022 | ICSE | https://doi.org/10.1145/3510003.3510081 | 83% of real-world OpenAPI specs missing ≥1 critical element | Motivates 7-gate validator |
| "Automated REST API Testing Using OpenAPI" | Martin-Lopez et al. | 2021 | FSE | https://doi.org/10.1145/3468264.3473126 | Spec-based test generation achieves 90%+ coverage vs manual | Motivates test_stub_generator |
| "An Empirical Study of GraphQL Schemas" | Wittern et al. | 2019 | ICSOC | https://arxiv.org/abs/1907.13580 | GraphQL schemas in the wild: avg depth 5, avg 47 types | GraphQL design metrics |
| "CodeT5+: Open Code Large Language Models" | Wang et al. | 2023 | EMNLP | https://arxiv.org/abs/2305.07922 | 770M encoder-decoder; SOTA on code generation/summarization at size | CodeT5+ reverse engineering |
| "Towards LLM-Powered Code Generation from OpenAPI Specifications" | Liu et al. | 2024 | ICSE | https://arxiv.org/abs/2404.01345 | Claude/GPT-4 generate valid REST clients from OpenAPI in 87% of cases | NL→spec generation baseline |
| "BOLA/IDOR: API Security Testing" | OWASP | 2023 | OWASP API Security Top 10 | https://owasp.org/API-Security/ | Authorization level object access is #1 API security flaw | Security schema validation |
| "BGE M3-Embedding: Multi-Lingual, Multi-Functionality" | Chen et al. | 2024 | arXiv | https://arxiv.org/abs/2402.03216 | BGE-large-en-v1.5 MTEB rank #1 dense; bge-m3 adds multilingual | Embedding model selection |
| "Semantic Similarity for OpenAPI Spec Recommendation" | Perez et al. | 2023 | ICWS | https://arxiv.org/abs/2309.11213 | Embedding-based spec retrieval outperforms keyword search by 38% | FAISS few-shot retrieval |
| "Test Generation from API Specifications" | Atlidakis et al. (RESTler) | 2019 | ICSE | https://arxiv.org/abs/1806.09739 | RESTler stateful REST API fuzzer; spec-driven test sequence generation | Motivates automated test stubs |
| "Design Patterns for RESTful APIs" | Richardson & Ruby | 2007 | O'Reilly RESTful Web Services | Book ISBN 978-0596529260 | CRUD mapping, hypertext-driven workflows, resource modeling | REST design advisor |
| "Comparing REST and GraphQL for API Design" | Brito et al. | 2020 | SBES | https://arxiv.org/abs/2003.08090 | REST better for simple CRUD; GraphQL better for complex nested reads | Pattern advisor decision signals |

---

## State-of-the-Art Models

| Model | Task | Score | Date | Notes |
|-------|------|-------|------|-------|
| `Salesforce/codet5p-770m` | Code→text, code understanding | HumanEval pass@1=0.311 (770M) | 2023-05 | Best code summarization at ≤1B params |
| `BAAI/bge-large-en-v1.5` | Dense text embedding | MTEB Avg 64.23 | 2023-09 | #1 on MTEB English at release; 1024-dim |
| `sentence-transformers/all-MiniLM-L6-v2` | Fast embedding | MTEB Avg 56.26 | 2021 | 6× faster than bge-large; 384-dim |
| `BAAI/bge-reranker-large` | Cross-encoder reranking | BEIR nDCG@10=0.593 | 2023-09 | Best open reranker on BEIR benchmark |
| `claude-opus-4-8` | Long-context reasoning, YAML generation | MMLU 86.8, HumanEval 84.9 | 2025 | Primary LLM for spec generation |
| `gpt-4o` | Multimodal, structured output | MMLU 88.7 | 2024 | Fallback; strong JSON/YAML mode |
| `llama3` (8B, Ollama) | Offline generation | MMLU 68.4 | 2024 | Privacy mode; no API key required |

---

## LLM Prompt Patterns

### 1. NL → OpenAPI Spec Generation

```
SYSTEM:
You are an expert API designer. Generate a complete, valid OpenAPI 3.0.3 YAML specification
from the user's natural language description. Requirements:
- Include ALL likely status codes: 200/201/400/401/403/404/422/500
- Define a reusable Error schema in components/schemas/Error (RFC 7807 style)
- Add authentication: JWT Bearer unless otherwise specified
- Write descriptions for every path, operation, and parameter
- Include at least one request and response example
- Output ONLY valid YAML, no markdown fences

USER:
{{nl_description}}

Existing schemas context: {{existing_schemas_json}}
```

### 2. Spec Validation Issue Explanation

```
SYSTEM:
You are a senior API reviewer. Given validation issues found in an OpenAPI spec,
provide a clear, actionable explanation and a concrete YAML fix example for each issue.
Output as JSON array: [{"issue_id": str, "explanation": str, "yaml_fix": str}]

USER:
Issues: {{issues_json}}
Failing spec excerpt: {{yaml_excerpt}}
```

### 3. Test Stub Generation

```
SYSTEM:
You are a test engineer. From the following OpenAPI 3.0 spec, generate {{framework}} test stubs.
For each operation include:
1. Happy path test (expected 2xx)
2. Not found test (404 where applicable)
3. Validation error test (422/400 with bad request body)
4. Unauthorized test (401 with missing/invalid token)
5. One edge case specific to the operation semantics

Use {{pytest_conventions | jest_conventions}}.

USER:
Spec: {{spec_yaml}}
Base URL: {{base_url}}
```

### 4. Protocol Pattern Advisor

```
SYSTEM:
You are a senior API architect. Analyze the use case and recommend REST, GraphQL, or AsyncAPI.
Your recommendation must consider:
- Query complexity and nesting depth
- Real-time / event-driven requirements
- Team expertise and toolchain
- CAP theorem implications
- Mobile / bandwidth constraints

Return JSON: {"recommendation": str, "confidence": float, "rationale": str,
"trade_offs": {"REST": {...}, "GraphQL": {...}, "AsyncAPI": {...}}, "starter_spec_snippet": str}

USER:
Use case: {{use_case}}
Constraints: {{constraints_json}}
```

---

## Authoritative Data Sources

| Source | URL | Type | Update Frequency |
|--------|-----|------|-----------------|
| OpenAPI Specification | https://spec.openapis.org/oas/latest.html | Standard | Per release |
| AsyncAPI Specification | https://www.asyncapi.com/docs/reference/specification/latest | Standard | Per release |
| GraphQL Spec | https://spec.graphql.org/ | Standard | Per release |
| OWASP API Security Top 10 | https://owasp.org/API-Security/ | Security | Annual |
| Swagger/OpenAPI Tools | https://swagger.io/tools/ | Tooling | Continuous |
| ArXiv cs.SE | https://arxiv.org/list/cs.SE/recent | Research | Daily |
| Semantic Scholar API | https://api.semanticscholar.org/graph/v1/paper/search | Research | Continuous |
| Papers with Code — Code Gen | https://paperswithcode.com/task/code-generation | Leaderboards | Weekly |
| OpenAPI Initiative Blog | https://www.openapis.org/blog | Industry | Monthly |
| GitHub: OAI/OpenAPI-Specification | https://github.com/OAI/OpenAPI-Specification/releases | Releases | Per release |
| RFC 7807 Problem Details | https://datatracker.ietf.org/doc/html/rfc7807 | Standard | Stable |
| HuggingFace Papers | https://huggingface.co/papers | Research | Daily |

---

## Self-Update Protocol

```yaml
knowledge_updater_config:
  schedule: "weekly Sunday 02:00 local"
  
  sources:
    arxiv:
      categories: ["cs.SE", "cs.PL"]
      max_results: 50
      lookback_days: 90
      
    semantic_scholar:
      queries:
        - "OpenAPI specification generation"
        - "REST API design automation"
        - "GraphQL schema design"
        - "API test generation specification"
        - "natural language to API specification"
      max_results_per_query: 20
      
    github_releases:
      repos:
        - "OAI/OpenAPI-Specification"
        - "swagger-api/swagger-codegen"
        - "APIDevTools/openapi-typescript"
        - "stoplightio/spectral"
        - "pb33f/libopenapi"
      
  scoring:
    recency_weight: 0.6   # last 90 days = max score
    relevance_weight: 0.4  # keyword match in title+abstract
    keywords: ["OpenAPI", "API design", "REST", "GraphQL", "AsyncAPI",
               "API specification", "test generation", "API validation",
               "LLM code generation", "API schema"]
    
  output:
    top_n: 10
    append_to: "SECOND-KNOWLEDGE-BRAIN.md"
    section: "## Knowledge Update Log"
    dedup_via: "SHA256(DOI or URL)"
```

---

## Knowledge Update Log

### 2026-06-09 — Initial Seed (15 entries)

| # | Title | Source | Date | Relevance |
|---|-------|--------|------|-----------|
| 1 | "REST: Architectural Styles..." (Fielding dissertation) | Manual | 2000 | Foundation |
| 2 | "Problem Details for HTTP APIs" RFC 7807 | Manual | 2016 | Error schema gate |
| 3 | "Evaluating Consistency of OpenAPI Specs" (Vaziri, ICSE 2022) | Manual | 2022 | Validator motivation |
| 4 | "Automated REST API Testing Using OpenAPI" (FSE 2021) | Manual | 2021 | Test stub motivation |
| 5 | "An Empirical Study of GraphQL Schemas" (Wittern 2019) | Manual | 2019 | GraphQL advisor |
| 6 | "CodeT5+: Open Code LLMs" (Wang, EMNLP 2023) | Manual | 2023 | HF model selection |
| 7 | "Towards LLM-Powered Code Gen from OpenAPI" (Liu 2024) | Manual | 2024 | NL-to-spec baseline |
| 8 | "OWASP API Security Top 10 2023" | Manual | 2023 | Security gate |
| 9 | "BGE M3-Embedding" (Chen 2024) | Manual | 2024 | Embedding model |
| 10 | "Semantic Similarity for OpenAPI Recommendation" (Perez 2023) | Manual | 2023 | FAISS retrieval |
| 11 | "RESTler: Stateful REST API Fuzzer" (Atlidakis ICSE 2019) | Manual | 2019 | Test generation |
| 12 | "Comparing REST and GraphQL" (Brito 2020) | Manual | 2020 | Pattern advisor |
| 13 | "Spectral v6 — OpenAPI Linting Rules" (Stoplight) | Manual | 2024 | Validator implementation |
| 14 | "AsyncAPI 3.0 Specification Release" | Manual | 2023 | AsyncAPI advisor |
| 15 | "OpenAPI 3.1 JSON Schema Alignment" (OAI Blog) | Manual | 2021 | OAS 3.1 opt-in |
