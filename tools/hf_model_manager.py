"""HFModelManager — lazy-loading HuggingFace model registry for speckit-enhanced."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent


def get_models_dir() -> Path:
    """Get the models cache directory from config or default."""
    try:
        from agent.config import get_config
        config = get_config()
        return Path(config.get("agent.models_dir", "./models"))
    except Exception:
        return ROOT / "models"


MODELS_DIR = get_models_dir()

logger = logging.getLogger(__name__)

MODEL_REGISTRY = {
    "codet5p": "Salesforce/codet5p-770m",
    "bge_large": "BAAI/bge-large-en-v1.5",
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",
    "bge_reranker": "BAAI/bge-reranker-large",
}


class HFModelManager:
    """
    Singleton manager for HuggingFace models used in speckit-enhanced.

    Models:
    - codet5p: Salesforce/codet5p-770m — code→text summarization + code analysis
    - bge_large: BAAI/bge-large-en-v1.5 — dense text embedding (1024-dim)
    - minilm: all-MiniLM-L6-v2 — fast embedding (384-dim)
    - bge_reranker: BAAI/bge-reranker-large — cross-encoder reranking

    All models are lazily loaded on first use and unloaded after 600s of inactivity.
    """

    _instance: Optional["HFModelManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._models: dict = {}
        self._timers: dict[str, threading.Timer] = {}
        self._device = self._detect_device()
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def instance(cls) -> "HFModelManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = HFModelManager()
        return cls._instance

    def _detect_device(self) -> str:
        """Detect the best available device (CUDA, MPS, or CPU)."""
        try:
            import torch

            if torch.cuda.is_available():
                device_count = torch.cuda.device_count()
                device_name = torch.cuda.get_device_name(0) if device_count > 0 else "CUDA"
                logger.info("Using CUDA device: %s (%d device(s))", device_name, device_count)
                return "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                logger.info("Using Apple MPS (Metal Performance Shaders) device")
                return "mps"
            else:
                logger.info("No GPU detected, using CPU")
                return "cpu"
        except ImportError:
            logger.warning("PyTorch not available, using CPU")
            return "cpu"
        except Exception as e:
            logger.warning("Device detection failed: %s, using CPU", e)
            return "cpu"

    def _load_model(self, key: str):
        model_id = MODEL_REGISTRY[key]
        logger.info("Loading HuggingFace model: %s (device=%s)", model_id, self._device)

        # Determine device mapping
        device_map = self._device
        if self._device == "cuda":
            device_map = 0  # CUDA device index
        elif self._device == "mps":
            device_map = "mps"  # Apple Silicon
        else:
            device_map = -1  # CPU

        try:
            if key in ("bge_large", "minilm"):
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer(
                    model_id,
                    cache_folder=str(MODELS_DIR),
                    device=self._device
                )
                self._models[key] = ("sentence_transformer", model)

            elif key == "bge_reranker":
                from sentence_transformers import CrossEncoder
                model = CrossEncoder(
                    model_id,
                    max_length=512,
                    device=device_map
                )
                self._models[key] = ("cross_encoder", model)

            elif key == "codet5p":
                from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
                tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=str(MODELS_DIR))
                pipe = pipeline(
                    "summarization",
                    model=model_id,
                    tokenizer=tokenizer,
                    device=device_map,
                )
                self._models[key] = ("pipeline", pipe)

            logger.info("Successfully loaded model: %s", model_id)
            self._reset_idle_timer(key)

        except MemoryError as e:
            logger.error("Out of memory loading model %s: %s", model_id, e)
            self._models[key] = None
            self._cleanup_memory()
        except OSError as e:
            logger.error("Network or disk error loading model %s: %s", model_id, e)
            self._models[key] = None
        except Exception as e:
            logger.error("Failed to load model %s: %s", model_id, e)
            self._models[key] = None

    def _reset_idle_timer(self, key: str):
        if key in self._timers:
            self._timers[key].cancel()
        timer = threading.Timer(600.0, self._unload_model, args=[key])
        timer.daemon = True
        timer.start()
        self._timers[key] = timer

    def _unload_model(self, key: str):
        with self._lock:
            if key in self._models:
                logger.info("Unloading idle model: %s", MODEL_REGISTRY.get(key, key))
                del self._models[key]
                self._cleanup_memory()

    def _cleanup_memory(self):
        """Clean up memory after model unload."""
        try:
            import gc
            gc.collect()

            if self._device == "cuda":
                try:
                    import torch
                    torch.cuda.empty_cache()
                    logger.debug("CUDA cache cleared")
                except ImportError:
                    pass
            elif self._device == "mps":
                try:
                    import torch
                    torch.mps.empty_cache()
                    logger.debug("MPS cache cleared")
                except (ImportError, AttributeError):
                    pass
        except Exception as e:
            logger.warning("Memory cleanup failed: %s", e)

    def _get_model(self, key: str):
        with self._lock:
            if key not in self._models:
                self._load_model(key)
            else:
                self._reset_idle_timer(key)
        return self._models.get(key)

    # ── Public API ─────────────────────────────────────────────────────────────

    def encode(self, text: str, model_key: str = "bge_large") -> list[float]:
        """Encode a single text to a dense embedding vector."""
        entry = self._get_model(model_key)
        if entry is None:
            return self._tfidf_fallback(text)
        kind, model = entry
        if kind == "sentence_transformer":
            import numpy as np
            emb = model.encode(text, normalize_embeddings=True)
            return emb.tolist()
        return self._tfidf_fallback(text)

    def encode_batch(self, texts: list[str], model_key: str = "bge_large", batch_size: int = 32) -> list[list[float]]:
        """Encode a batch of texts."""
        entry = self._get_model(model_key)
        if entry is None:
            return [self._tfidf_fallback(t) for t in texts]
        kind, model = entry
        if kind == "sentence_transformer":
            results = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                embs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
                results.extend(embs.tolist())
            return results
        return [self._tfidf_fallback(t) for t in texts]

    def rerank(self, query: str, passages: list[str], top_k: int = 5) -> list[tuple[int, float]]:
        """Cross-encoder reranking. Returns list of (original_index, score) sorted by score desc."""
        entry = self._get_model("bge_reranker")
        if entry is None or entry[0] != "cross_encoder":
            return self._heuristic_rerank(query, passages, top_k)
        _, model = entry
        pairs = [[query, p] for p in passages]
        try:
            scores = model.predict(pairs)
            ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            return ranked[:top_k]
        except Exception as e:
            logger.warning("BGE reranker failed: %s", e)
            return self._heuristic_rerank(query, passages, top_k)

    def analyze_code(self, code: str, task: str = "summarize") -> str:
        """Use CodeT5+ to summarize/analyze code (code→text)."""
        entry = self._get_model("codet5p")
        if entry is None:
            return self._simple_code_analysis(code)
        kind, pipe = entry
        if kind == "pipeline":
            try:
                result = pipe(code[:1024], max_length=150, min_length=20, do_sample=False)
                return result[0].get("summary_text", "") if result else ""
            except Exception as e:
                logger.warning("CodeT5+ pipeline failed: %s", e)
                return self._simple_code_analysis(code)
        return self._simple_code_analysis(code)

    def preload(self, keys: list[str] = None):
        """Pre-load specified models (or all) in background."""
        keys = keys or list(MODEL_REGISTRY.keys())
        for key in keys:
            threading.Thread(target=self._get_model, args=(key,), daemon=True).start()

    def build_faiss_index(self, texts: list[str], save_path: Path = None) -> bool:
        """Build a FAISS index from a list of texts for similarity search."""
        try:
            import faiss
            import numpy as np

            logger.info("Building FAISS index from %d texts", len(texts))

            # Encode texts
            embeddings = self.encode_batch(texts, model_key="bge_large", batch_size=32)
            embeddings_np = np.array(embeddings, dtype=np.float32)

            # Normalize for cosine similarity
            faiss.normalize_L2(embeddings_np)

            # Build index
            dimension = embeddings_np.shape[1]
            index = faiss.IndexFlatIP(dimension)
            index.add(embeddings_np)

            # Save if path provided
            if save_path:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                faiss.write_index(index, str(save_path))
                logger.info("FAISS index saved to %s", save_path)

            return True
        except Exception as e:
            logger.error("Failed to build FAISS index: %s", e)
            return False

    # ── Fallbacks ──────────────────────────────────────────────────────────────

    def _tfidf_fallback(self, text: str) -> list[float]:
        """Deterministic hash-based pseudo-embedding fallback (CPU, no deps)."""
        import hashlib
        import math
        words = text.lower().split()
        vec = [0.0] * 384
        for w in words[:50]:
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            idx = h % 384
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def _heuristic_rerank(self, query: str, passages: list[str], top_k: int) -> list[tuple[int, float]]:
        """Keyword overlap reranking fallback."""
        query_words = set(query.lower().split())
        scored = []
        for i, p in enumerate(passages):
            p_words = set(p.lower().split())
            score = len(query_words & p_words) / max(len(query_words), 1)
            scored.append((i, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _simple_code_analysis(self, code: str) -> str:
        """Regex-based code route extraction when CodeT5+ is unavailable."""
        import re
        routes = re.findall(
            r'@(?:app|router|blueprint|r)\.(get|post|put|patch|delete|route)\(["\']([^"\']+)["\']',
            code, re.IGNORECASE
        )
        if routes:
            return "Detected routes: " + ", ".join(f"{m.upper()} {p}" for m, p in routes)
        return "No route annotations detected in code excerpt."
