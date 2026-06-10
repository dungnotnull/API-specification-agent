"""KnowledgeUpdater — crawl ArXiv cs.SE + Semantic Scholar + GitHub releases → SECOND-KNOWLEDGE-BRAIN.md."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
BRAIN_PATH = ROOT / "SECOND-KNOWLEDGE-BRAIN.md"
DATA_DIR = ROOT / "data"

logger = logging.getLogger(__name__)

ARXIV_CATEGORIES = ["cs.SE", "cs.PL"]
ARXIV_SEARCH_TERMS = [
    "OpenAPI specification",
    "REST API design",
    "API test generation",
    "natural language API",
    "software specification",
]

SEMANTIC_SCHOLAR_QUERIES = [
    "OpenAPI specification generation",
    "REST API design automation",
    "GraphQL schema design",
    "API test generation specification",
    "natural language to API specification",
]

GITHUB_REPOS = [
    "OAI/OpenAPI-Specification",
    "swagger-api/swagger-codegen",
    "APIDevTools/openapi-typescript",
    "stoplightio/spectral",
    "pb33f/libopenapi",
]

RELEVANCE_KEYWORDS = [
    "openapi", "api design", "rest", "graphql", "asyncapi",
    "api specification", "test generation", "api validation",
    "swagger", "specification", "endpoint", "schema", "llm",
]


class PaperEntry:
    def __init__(self, title: str, authors: str, year: str, url: str, abstract: str, source: str):
        self.title = title
        self.authors = authors
        self.year = year
        self.url = url
        self.abstract = abstract
        self.source = source
        self._score_cache = None

    def relevance_score(self) -> float:
        """Calculate relevance score based on keywords and recency."""
        if self._score_cache is not None:
            return self._score_cache

        text = (self.title + " " + self.abstract).lower()
        keyword_hits = sum(1 for kw in RELEVANCE_KEYWORDS if kw in text)

        try:
            year_val = int(self.year)
            current_year = datetime.now().year
            years_ago = max(0, current_year - year_val)
            recency = max(0, 1.0 - (years_ago / 10.0))  # Decay over 10 years
        except (ValueError, AttributeError):
            recency = 0.5

        # Weight: 60% keyword relevance, 40% recency
        score = (keyword_hits / len(RELEVANCE_KEYWORDS)) * 0.6 + recency * 0.4
        self._score_cache = min(score, 1.0)
        return self._score_cache

    def url_hash(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()

    def to_brain_row(self) -> str:
        short_title = self.title[:80] + "..." if len(self.title) > 80 else self.title
        short_abstract = self.abstract[:200] + "..." if len(self.abstract) > 200 else self.abstract
        score = self.relevance_score()
        return (
            f"| {short_title} | {self.authors[:40]} | {self.year} | {self.source} "
            f"| {self.url} | {short_abstract} | {score:.2f} |"
        )


class KnowledgeUpdater:
    def __init__(self):
        self._memory = None
        self._session = None

    def _get_memory(self):
        if self._memory is None:
            import sys
            sys.path.insert(0, str(ROOT))
            from agent.memory.memory_manager import MemoryManager
            self._memory = MemoryManager()
        return self._memory

    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def run_update(self) -> dict:
        """Main entry point. Returns: entries_added, sources_crawled, next_scheduled."""
        logger.info("Starting knowledge update crawl...")
        entries: list[PaperEntry] = []

        sources_crawled = []
        errors = []

        # ArXiv
        try:
            arxiv_entries = await self._crawl_arxiv()
            entries.extend(arxiv_entries)
            sources_crawled.append(f"arxiv ({len(arxiv_entries)} entries)")
        except Exception as e:
            logger.error("ArXiv crawl failed: %s", e)
            errors.append(f"ArXiv: {str(e)}")

        # Semantic Scholar
        try:
            ss_entries = await self._crawl_semantic_scholar()
            entries.extend(ss_entries)
            sources_crawled.append(f"semantic_scholar ({len(ss_entries)} entries)")
        except Exception as e:
            logger.error("Semantic Scholar crawl failed: %s", e)
            errors.append(f"Semantic Scholar: {str(e)}")

        # GitHub releases
        try:
            gh_entries = await self._crawl_github_releases()
            entries.extend(gh_entries)
            sources_crawled.append(f"github ({len(gh_entries)} entries)")
        except Exception as e:
            logger.error("GitHub crawl failed: %s", e)
            errors.append(f"GitHub: {str(e)}")

        # Score + deduplicate
        entries.sort(key=lambda e: e.relevance_score(), reverse=True)
        new_entries = []
        memory = self._get_memory()
        for entry in entries[:50]:
            if not memory.is_known_paper(entry.url):
                new_entries.append(entry)
                memory.mark_paper_known(entry.url, entry.title)

        # Append top 10 to SECOND-KNOWLEDGE-BRAIN.md
        top = new_entries[:10]
        if top:
            self._append_to_brain(top)

        logger.info("Knowledge update complete: %d new entries added", len(top))
        if errors:
            logger.warning("Crawl errors: %s", errors)

        return {
            "entries_added": len(top),
            "sources_crawled": sources_crawled,
            "next_scheduled": "Next Sunday 02:00 (weekly)",
            "errors": errors,
        }

    async def _crawl_arxiv(self) -> list[PaperEntry]:
        session = await self._get_session()
        entries = []
        categories = "+OR+".join(f"cat:{c}" for c in ARXIV_CATEGORIES)
        terms = "+OR+".join(f'ti:"{t}"' for t in ARXIV_SEARCH_TERMS[:3])
        query = f"({categories})+AND+({terms})"
        url = f"http://export.arxiv.org/api/query?search_query={query}&max_results=40&sortBy=lastUpdatedDate"

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error("ArXiv returned HTTP %d", resp.status)
                    return entries
                text = await resp.text()

            ns = {"atom": "http://www.w3.org/2005/Atom"}
            root = ET.fromstring(text)
            for entry in root.findall("atom:entry", ns):
                title = (entry.findtext("atom:title", namespaces=ns) or "").strip().replace("\n", " ")
                abstract = (entry.findtext("atom:summary", namespaces=ns) or "").strip().replace("\n", " ")
                published = entry.findtext("atom:published", namespaces=ns) or ""
                year = published[:4] if published else "?"
                link_elem = entry.find("atom:id", ns)
                url = link_elem.text.strip() if link_elem is not None else ""
                authors = ", ".join(
                    a.findtext("atom:name", namespaces=ns) or ""
                    for a in entry.findall("atom:author", ns)
                )[:60]
                if title and url:
                    entries.append(PaperEntry(title, authors, year, url, abstract, "ArXiv"))

        except Exception as e:
            logger.error("ArXiv parsing failed: %s", e)

        return entries

    async def _crawl_semantic_scholar(self) -> list[PaperEntry]:
        session = await self._get_session()
        entries = []
        base = "https://api.semanticscholar.org/graph/v1/paper/search"
        fields = "title,authors,year,externalIds,abstract"

        for query in SEMANTIC_SCHOLAR_QUERIES[:3]:
            try:
                params = {"query": query, "limit": 10, "fields": fields}
                async with session.get(base, params=params) as resp:
                    if resp.status != 200:
                        logger.warning("Semantic Scholar returned HTTP %d for query: %s", resp.status, query)
                        continue
                    data = await resp.json()

                for paper in (data.get("data") or []):
                    title = paper.get("title") or ""
                    year = str(paper.get("year") or "?")
                    abstract = paper.get("abstract") or ""
                    doi = (paper.get("externalIds") or {}).get("DOI", "")
                    arxiv_id = (paper.get("externalIds") or {}).get("ArXiv", "")
                    url = f"https://doi.org/{doi}" if doi else (
                        f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
                    )
                    authors = ", ".join(
                        a.get("name", "") for a in (paper.get("authors") or [])[:3]
                    )
                    if title and url:
                        entries.append(PaperEntry(title, authors, year, url, abstract, "Semantic Scholar"))

                await asyncio.sleep(1)  # Rate limiting
            except asyncio.TimeoutError:
                logger.warning("Semantic Scholar timeout for query: %s", query)
            except Exception as e:
                logger.warning("Semantic Scholar query '%s' failed: %s", query, e)

        return entries

    async def _crawl_github_releases(self) -> list[PaperEntry]:
        session = await self._get_session()
        entries = []

        for repo in GITHUB_REPOS[:4]:
            try:
                url = f"https://api.github.com/repos/{repo}/releases/latest"
                headers = {
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "speckit-enhanced"
                }
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning("GitHub returned HTTP %d for repo: %s", resp.status, repo)
                        continue
                    data = await resp.json()

                tag = data.get("tag_name", "")
                published = data.get("published_at", "")[:4]
                title = f"{repo} release {tag}"
                body = (data.get("body") or "")[:300]
                html_url = data.get("html_url", "")
                entries.append(PaperEntry(title, repo, published, html_url, body, "GitHub Releases"))

                await asyncio.sleep(0.5)  # Rate limiting
            except asyncio.TimeoutError:
                logger.warning("GitHub timeout for repo: %s", repo)
            except Exception as e:
                logger.warning("GitHub release fetch for %s failed: %s", repo, e)

        return entries

    def _append_to_brain(self, entries: list[PaperEntry]):
        if not BRAIN_PATH.exists():
            logger.error("SECOND-KNOWLEDGE-BRAIN.md not found at %s", BRAIN_PATH)
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_lines = [
            "",
            f"### {now} — Automated Crawl ({len(entries)} new entries)",
            "",
            "| Title | Authors | Year | Source | URL | Key Finding | Relevance |",
            "|-------|---------|------|--------|-----|-------------|-----------|",
        ]
        for e in entries:
            new_lines.append(e.to_brain_row())

        brain_text = BRAIN_PATH.read_text(encoding="utf-8")
        section_marker = "## Knowledge Update Log"
        if section_marker in brain_text:
            idx = brain_text.index(section_marker) + len(section_marker)
            updated = brain_text[:idx] + "\n" + "\n".join(new_lines) + "\n" + brain_text[idx:]
        else:
            updated = brain_text + "\n" + "\n".join(new_lines) + "\n"

        BRAIN_PATH.write_text(updated, encoding="utf-8")
        logger.info("Appended %d entries to SECOND-KNOWLEDGE-BRAIN.md", len(entries))


def start_scheduled():
    """Start APScheduler for weekly knowledge updates."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        updater = KnowledgeUpdater()
        scheduler = BlockingScheduler()
        scheduler.add_job(
            func=lambda: asyncio.run(updater.run_update()),
            trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
            id="weekly_knowledge_update",
        )
        logger.info("Knowledge updater scheduled: weekly Sunday 02:00")
        scheduler.start()
    except ImportError:
        logger.error("APScheduler not installed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(KnowledgeUpdater().run_update())
    print(f"Done: {result}")
