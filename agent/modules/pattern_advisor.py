"""PatternAdvisor — recommend REST, GraphQL, or AsyncAPI for an API use case."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)

PATTERN_ADVISOR_PROMPT = """You are a senior API architect. Analyze the use case and recommend the best API protocol.

Protocols to consider:
- REST: best for CRUD, resource-oriented, public APIs, wide toolchain support
- GraphQL: best for complex nested queries, rapid client iteration, mobile with bandwidth constraints, multiple consumers needing different shapes
- AsyncAPI: best for real-time/event-driven, notifications, streaming, IoT, financial ticks
- REST+AsyncAPI: combined when CRUD + real-time notifications both needed

Your response MUST be valid JSON with this exact structure:
{
  "recommendation": "REST" | "GraphQL" | "AsyncAPI" | "REST+AsyncAPI",
  "confidence": 0.0-1.0,
  "rationale": "3-5 sentence explanation referencing CAP theorem, query patterns, real-time requirements",
  "trade_offs": {
    "REST": {"pros": ["..."], "cons": ["..."]},
    "GraphQL": {"pros": ["..."], "cons": ["..."]},
    "AsyncAPI": {"pros": ["..."], "cons": ["..."]}
  },
  "starter_spec_snippet": "minimal YAML spec snippet in the recommended protocol"
}

Return ONLY the JSON object. No markdown. No explanation outside the JSON."""

# Decision signals for heuristic fallback
ASYNC_SIGNALS = [
    "real-time", "realtime", "streaming", "notification", "event", "push", "subscribe",
    "websocket", "mqtt", "kafka", "iot", "sensor", "ticker", "feed", "live",
]
GRAPHQL_SIGNALS = [
    "complex", "nested", "query", "flexible", "mobile", "bandwidth", "multiple clients",
    "different shapes", "partial", "graph", "relationship", "social",
]
REST_SIGNALS = [
    "crud", "resource", "simple", "public", "standard", "rest", "http",
    "create", "read", "update", "delete", "list", "fetch",
]

REST_SNIPPET = """\
openapi: "3.0.3"
info:
  title: "My API"
  version: "1.0.0"
paths:
  /resources:
    get:
      summary: "List resources"
      responses:
        "200":
          description: "Success"
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Resource'
"""

GRAPHQL_SNIPPET = """\
# GraphQL Schema Definition Language (SDL)
type Query {
  resource(id: ID!): Resource
  resources(limit: Int, offset: Int): [Resource!]!
}

type Mutation {
  createResource(input: CreateResourceInput!): Resource!
  updateResource(id: ID!, input: UpdateResourceInput!): Resource!
  deleteResource(id: ID!): Boolean!
}

type Resource {
  id: ID!
  name: String!
  createdAt: String!
}
"""

ASYNCAPI_SNIPPET = """\
asyncapi: "3.0.0"
info:
  title: "My Event API"
  version: "1.0.0"
channels:
  resource/created:
    messages:
      ResourceCreated:
        payload:
          type: object
          properties:
            id:
              type: string
            name:
              type: string
            createdAt:
              type: string
              format: date-time
"""

STARTER_SPECS = {
    "REST": REST_SNIPPET,
    "GraphQL": GRAPHQL_SNIPPET,
    "AsyncAPI": ASYNCAPI_SNIPPET,
    "REST+AsyncAPI": REST_SNIPPET + "\n---\n" + ASYNCAPI_SNIPPET,
}


class PatternAdvisor:
    """
    Recommends REST, GraphQL, or AsyncAPI for a given use case.

    Primary: LLM-based analysis with FAISS retrieval of similar past recommendations.
    Fallback: keyword heuristic scoring.
    """

    def __init__(self):
        self._llm = None
        self._hf = None
        self._faiss_index = None
        self._faiss_texts = []
        self._faiss_embeddings = None
        self._index_path = ROOT / "data" / "pattern_advisor_faiss.index"
        self._texts_path = ROOT / "data" / "pattern_advisor_texts.json"

        # Load FAISS index if exists
        self._load_faiss_index()

    def _get_llm(self):
        if self._llm is None:
            import sys
            sys.path.insert(0, str(ROOT))
            from tools.llm_client import UnifiedLLMClient
            self._llm = UnifiedLLMClient()
        return self._llm

    def _get_hf(self):
        if self._hf is None:
            import sys
            sys.path.insert(0, str(ROOT))
            from tools.hf_model_manager import HFModelManager
            self._hf = HFModelManager.instance()
        return self._hf

    async def advise(self, use_case: str, constraints: dict = None) -> dict:
        """
        Recommend API protocol for a use case.

        Returns dict: recommendation, confidence, rationale, trade_offs, starter_spec_snippet
        """
        constraints = constraints or {}

        # Build FAISS query for similar past recommendations
        similar_examples = self._retrieve_similar_examples(use_case)

        # Build enhanced user message with similar examples
        examples_text = ""
        if similar_examples:
            examples_text = "\n\nSimilar past use cases and their recommendations:\n"
            for i, (rec, score) in enumerate(similar_examples[:3], 1):
                examples_text += f"{i}. Recommended: {rec} (similarity: {score:.2f})\n"

        user_msg = f"Use case: {use_case}\n{examples_text}\n\nConstraints: {json.dumps(constraints, indent=2)}"

        try:
            raw = await self._get_llm().complete(
                system=PATTERN_ADVISOR_PROMPT,
                user=user_msg,
                task="pattern_advisory",
                max_tokens=1500,
            )
            result = self._parse_json_response(raw)
            if result:
                # Ensure starter_spec_snippet is always populated
                if not result.get("starter_spec_snippet"):
                    result["starter_spec_snippet"] = STARTER_SPECS.get(result["recommendation"], REST_SNIPPET)

                # Save this recommendation to FAISS index
                self._add_to_faiss_index(use_case, result["recommendation"])

                return result
        except Exception as e:
            logger.warning("LLM pattern advisor failed: %s", e)

        # Fallback: heuristic scoring
        return self._heuristic_advise(use_case, constraints)

    # ── FAISS Index Management ─────────────────────────────────────────────────────

    def _load_faiss_index(self):
        """Load FAISS index from disk if it exists."""
        if not self._index_path.exists():
            return

        try:
            import faiss
            self._faiss_index = faiss.read_index(str(self._index_path))
            if self._texts_path.exists():
                self._faiss_texts = json.loads(self._texts_path.read_text())
            logger.info("Loaded FAISS index with %d entries", len(self._faiss_texts))
        except Exception as e:
            logger.warning("Failed to load FAISS index: %s", e)

    def _build_faiss_index(self, max_entries: int = 50):
        """Build FAISS index from example use cases."""
        import faiss
        from tools.hf_model_manager import HFModelManager

        hf = HFModelManager.instance()

        # Example use cases for initial index (text, recommendation)
        examples = [
            ("CRUD API for user management with JWT authentication", "REST"),
            ("Real-time stock ticker with push notifications", "AsyncAPI"),
            ("Mobile app backend for social network with complex nested queries", "GraphQL"),
            ("E-commerce product catalog with filtering and search", "REST"),
            ("IoT sensor data streaming platform", "AsyncAPI"),
            ("Analytics dashboard with flexible report generation", "GraphQL"),
            ("Payment processing webhook system", "REST+AsyncAPI"),
            ("File upload and management service", "REST"),
            ("Chat application with online status indicators", "REST+AsyncAPI"),
            ("Content management system with headless CMS requirements", "REST"),
        ]

        texts = [t for t, _ in examples]
        recommendations = [r for _, r in examples]
        embeddings = hf.encode_batch(texts, model_key="minilm", batch_size=10)

        dimension = len(embeddings[0])
        index = faiss.IndexFlatIP(dimension)  # Inner product (cosine similarity with normalized vectors)

        import numpy as np
        embeddings_np = np.array(embeddings, dtype=np.float32)
        # Normalize for cosine similarity
        faiss.normalize_L2(embeddings_np)
        index.add(embeddings_np)

        self._faiss_index = index
        self._faiss_texts = recommendations  # Store recommendations, not texts

        # Save to disk
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(self._index_path))
        self._texts_path.write_text(json.dumps(recommendations))

        logger.info("Built FAISS index with %d example entries", len(examples))

    def _retrieve_similar_examples(self, use_case: str, top_k: int = 3) -> list:
        """Retrieve similar past use cases from FAISS index."""
        if self._faiss_index is None:
            self._build_faiss_index()

        if self._faiss_index is None:
            return []

        try:
            from tools.hf_model_manager import HFModelManager
            import numpy as np

            hf = HFModelManager.instance()
            query_emb = hf.encode(use_case, model_key="minilm")

            query_np = np.array([query_emb], dtype=np.float32)
            faiss.normalize_L2(query_np)

            k = min(top_k, self._faiss_index.ntotal)
            scores, indices = self._faiss_index.search(query_np, k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx < len(self._faiss_texts):
                    results.append((self._faiss_texts[idx], float(score)))

            return results
        except Exception as e:
            logger.warning("FAISS retrieval failed: %s", e)
            return []

    def _add_to_faiss_index(self, use_case: str, recommendation: str):
        """Add a new recommendation to the FAISS index."""
        try:
            from tools.hf_model_manager import HFModelManager
            import faiss
            import numpy as np

            hf = HFModelManager.instance()
            emb = hf.encode(use_case, model_key="minilm")

            emb_np = np.array([emb], dtype=np.float32)
            faiss.normalize_L2(emb_np)

            if self._faiss_index is None:
                self._build_faiss_index()

            self._faiss_index.add(emb_np)
            self._faiss_texts.append(recommendation)

            # Save updated index
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._faiss_index, str(self._index_path))
            self._texts_path.write_text(json.dumps(self._faiss_texts))

            logger.debug("Added recommendation to FAISS index: %s -> %s", use_case[:30], recommendation)
        except Exception as e:
            logger.warning("Failed to add to FAISS index: %s", e)

    async def advise(self, use_case: str, constraints: dict = None) -> dict:
        """
        Recommend API protocol for a use case.

        Returns dict: recommendation, confidence, rationale, trade_offs, starter_spec_snippet
        """
        constraints = constraints or {}
        user_msg = f"Use case: {use_case}\n\nConstraints: {json.dumps(constraints, indent=2)}"

        try:
            raw = await self._get_llm().complete(
                system=PATTERN_ADVISOR_PROMPT,
                user=user_msg,
                task="pattern_advisory",
                max_tokens=1500,
            )
            result = self._parse_json_response(raw)
            if result:
                # Ensure starter_spec_snippet is always populated
                if not result.get("starter_spec_snippet"):
                    result["starter_spec_snippet"] = STARTER_SPECS.get(result["recommendation"], REST_SNIPPET)
                return result
        except Exception as e:
            logger.warning("LLM pattern advisor failed: %s", e)

        # Fallback: heuristic scoring
        return self._heuristic_advise(use_case, constraints)

    def _parse_json_response(self, raw: str) -> dict | None:
        raw = raw.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            start, end = 1, len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            raw = "\n".join(lines[start:end])

        try:
            parsed = json.loads(raw)
            required = {"recommendation", "confidence", "rationale", "trade_offs", "starter_spec_snippet"}
            if not required.issubset(parsed.keys()):
                logger.warning("Advisor response missing keys: %s", required - set(parsed.keys()))
                return None
            return parsed
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error in advisor response: %s", e)
            return None

    def _heuristic_advise(self, use_case: str, constraints: dict) -> dict:
        """Keyword-matching fallback when LLM is unavailable."""
        use_case_lower = use_case.lower()

        async_score = sum(1 for kw in ASYNC_SIGNALS if kw in use_case_lower)
        graphql_score = sum(1 for kw in GRAPHQL_SIGNALS if kw in use_case_lower)
        rest_score = sum(1 for kw in REST_SIGNALS if kw in use_case_lower)

        scores = {"REST": rest_score, "GraphQL": graphql_score, "AsyncAPI": async_score}
        winner = max(scores, key=lambda k: scores[k])

        # Combined recommendation if both REST and async signals
        if rest_score > 0 and async_score > 0 and async_score >= rest_score:
            winner = "REST+AsyncAPI"

        total = sum(scores.values()) or 1
        confidence = max(scores.values()) / (total * 0.7)
        confidence = min(confidence, 0.75)  # cap heuristic confidence

        rationale_map = {
            "REST": (
                "The use case exhibits CRUD and resource-oriented characteristics. "
                "REST provides the widest toolchain support (Swagger UI, Postman, code generators) "
                "and is well understood by most API consumers. "
                "Stateless HTTP semantics map cleanly to the described operations. "
                "The Richardson Maturity Model Level 2 is sufficient for this use case."
            ),
            "GraphQL": (
                "The use case involves complex, nested data queries and multiple client types. "
                "GraphQL eliminates over-fetching and under-fetching by letting clients specify "
                "exactly the fields they need. The flexible schema enables rapid iteration without "
                "versioning. DataLoader can solve the N+1 problem for nested resolvers."
            ),
            "AsyncAPI": (
                "The use case requires real-time event streaming or push notifications. "
                "AsyncAPI provides the specification standard for event-driven architectures, "
                "supporting WebSockets, MQTT, Kafka, and other transports. "
                "Unlike REST polling, event-driven delivery reduces latency and server load."
            ),
            "REST+AsyncAPI": (
                "The use case combines resource management (CRUD) with real-time event streaming. "
                "REST handles synchronous operations while AsyncAPI handles the event-driven layer. "
                "This hybrid architecture is common in modern platforms (e.g., GitHub REST API + webhooks). "
                "Clients can poll via REST and subscribe to change events via WebSockets."
            ),
        }

        return {
            "recommendation": winner,
            "confidence": round(confidence, 2),
            "rationale": rationale_map.get(winner, "Based on keyword analysis of the use case."),
            "trade_offs": {
                "REST": {
                    "pros": ["Wide toolchain support", "Simple caching", "Easy versioning", "Stateless"],
                    "cons": ["Over/under-fetching", "Multiple round trips for nested data", "No real-time push"],
                },
                "GraphQL": {
                    "pros": ["No over-fetching", "Type-safe schema", "Single endpoint", "Rapid iteration"],
                    "cons": ["Complex caching", "N+1 problem risk", "Learning curve", "No native file upload"],
                },
                "AsyncAPI": {
                    "pros": ["Real-time push", "Low latency", "Event-driven", "Decoupled producers/consumers"],
                    "cons": ["Connection management overhead", "Harder to debug", "No standard request/response"],
                },
            },
            "starter_spec_snippet": STARTER_SPECS.get(winner, REST_SNIPPET),
        }
