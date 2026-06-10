"""MemoryManager — SQLite persistence for speckit-enhanced."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent.parent


def get_data_dir() -> Path:
    """Get the data directory from config or default."""
    try:
        from agent.config import get_config
        config = get_config()
        return Path(config.get("agent.data_dir", "./data"))
    except Exception:
        return ROOT / "data"


DATA_DIR = get_data_dir()
DB_PATH = DATA_DIR / "speckit.db"


class MemoryManager:
    """
    Thread-safe SQLite persistence layer.

    Tables:
      - specs: generated OpenAPI specs and metadata
      - validations: validation results per spec
      - test_stubs: generated test stubs
      - advisory_history: pattern advisor results
      - llm_cost_log: per-call token cost tracking
      - knowledge_hashes: SHA256 dedup for paper crawler
    """

    def __init__(self, db_path: Path = DB_PATH):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS specs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT,
                    spec_yaml TEXT NOT NULL,
                    validation_score REAL,
                    issues_json TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_specs_created ON specs(created_at);

                CREATE TABLE IF NOT EXISTS validations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spec_yaml_hash TEXT NOT NULL,
                    score REAL NOT NULL,
                    issues_json TEXT,
                    passed_gates TEXT,
                    failed_gates TEXT,
                    validated_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS test_stubs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spec_yaml_hash TEXT NOT NULL,
                    pytest_stubs TEXT,
                    jest_stubs TEXT,
                    test_count INTEGER,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS advisory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    use_case TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    confidence REAL,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS llm_cost_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    task TEXT NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost_usd REAL,
                    logged_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS knowledge_hashes (
                    hash TEXT PRIMARY KEY,
                    title TEXT,
                    added_at TEXT DEFAULT (datetime('now'))
                );
            """)
            conn.commit()
            conn.close()

    # ── Spec storage ──────────────────────────────────────────────────────────

    def save_spec(
        self,
        description: str,
        spec_yaml: str,
        validation_score: float = 0.0,
        validation_issues: list = None,
    ):
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO specs (description, spec_yaml, validation_score, issues_json) VALUES (?,?,?,?)",
                (description, spec_yaml, validation_score, json.dumps(validation_issues or [])),
            )
            conn.commit()
            conn.close()

    def get_recent_specs(self, limit: int = 10) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT id, description, validation_score, created_at FROM specs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    # ── Validation storage ────────────────────────────────────────────────────

    def save_validation(self, spec_yaml: str, score: float, issues: list):
        h = hashlib.sha256(spec_yaml.encode()).hexdigest()
        with self._lock:
            conn = self._connect()
            conn.execute(
                """INSERT OR REPLACE INTO validations
                   (spec_yaml_hash, score, issues_json) VALUES (?,?,?)""",
                (h, score, json.dumps(issues)),
            )
            conn.commit()
            conn.close()

    # ── Test stub storage ─────────────────────────────────────────────────────

    def save_test_stubs(
        self,
        spec_yaml: str,
        pytest_stubs: Optional[str],
        jest_stubs: Optional[str],
        test_count: int,
    ):
        h = hashlib.sha256(spec_yaml.encode()).hexdigest()
        with self._lock:
            conn = self._connect()
            conn.execute(
                """INSERT INTO test_stubs
                   (spec_yaml_hash, pytest_stubs, jest_stubs, test_count) VALUES (?,?,?,?)""",
                (h, pytest_stubs, jest_stubs, test_count),
            )
            conn.commit()
            conn.close()

    # ── Advisory storage ──────────────────────────────────────────────────────

    def save_advisory(self, use_case: str, recommendation: str, confidence: float):
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO advisory_history (use_case, recommendation, confidence) VALUES (?,?,?)",
                (use_case, recommendation, confidence),
            )
            conn.commit()
            conn.close()

    def get_advisory_history(self, limit: int = 20) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT use_case, recommendation, confidence, created_at FROM advisory_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    # ── LLM cost tracking ─────────────────────────────────────────────────────

    def log_llm_cost(self, provider: str, task: str, input_tokens: int, output_tokens: int, cost_usd: float):
        with self._lock:
            conn = self._connect()
            conn.execute(
                """INSERT INTO llm_cost_log
                   (provider, task, input_tokens, output_tokens, cost_usd) VALUES (?,?,?,?,?)""",
                (provider, task, input_tokens, output_tokens, cost_usd),
            )
            conn.commit()
            conn.close()

    def get_cost_summary(self) -> dict:
        with self._lock:
            conn = self._connect()
            total = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_cost_log").fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM llm_cost_log").fetchone()[0]

            by_provider_rows = conn.execute(
                "SELECT provider, SUM(cost_usd) FROM llm_cost_log GROUP BY provider"
            ).fetchall()

            by_task_rows = conn.execute(
                "SELECT task, SUM(cost_usd) FROM llm_cost_log GROUP BY task"
            ).fetchall()

            conn.close()

            return {
                "total_usd": round(float(total), 6),
                "call_count": count,
                "by_provider": {r[0]: round(float(r[1]), 6) for r in by_provider_rows},
                "by_operation": {r[0]: round(float(r[1]), 6) for r in by_task_rows},
            }

    # ── Knowledge dedup ───────────────────────────────────────────────────────

    def is_known_paper(self, url_or_doi: str) -> bool:
        h = hashlib.sha256(url_or_doi.encode()).hexdigest()
        with self._lock:
            conn = self._connect()
            exists = conn.execute(
                "SELECT 1 FROM knowledge_hashes WHERE hash = ?", (h,)
            ).fetchone()
            conn.close()
            return exists is not None

    def mark_paper_known(self, url_or_doi: str, title: str = ""):
        h = hashlib.sha256(url_or_doi.encode()).hexdigest()
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT OR IGNORE INTO knowledge_hashes (hash, title) VALUES (?,?)",
                (h, title),
            )
            conn.commit()
            conn.close()

    def get_stats(self) -> dict:
        with self._lock:
            conn = self._connect()
            stats = {
                "total_specs": conn.execute("SELECT COUNT(*) FROM specs").fetchone()[0],
                "total_validations": conn.execute("SELECT COUNT(*) FROM validations").fetchone()[0],
                "total_test_stubs": conn.execute("SELECT COUNT(*) FROM test_stubs").fetchone()[0],
                "total_advisories": conn.execute("SELECT COUNT(*) FROM advisory_history").fetchone()[0],
                "known_papers": conn.execute("SELECT COUNT(*) FROM knowledge_hashes").fetchone()[0],
            }
            conn.close()
            return stats
