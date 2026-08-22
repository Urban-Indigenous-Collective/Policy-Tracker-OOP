"""Crawl configured state government sources for MMIP policy links."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterator

from discovery.browser_fetcher import BrowserRenderer
from discovery.fetchers import ApiFetcher, HttpFetcher, IndexFetcher, RssFetcher, SearchFetcher
from discovery.models import Candidate
from discovery.progress import get_progress
from discovery.source_schema import StateSource, load_sources_data

logger = logging.getLogger(__name__)

DEFAULT_SOURCES_PATH = Path(__file__).resolve().parent.parent / "sources" / "state_sources.json"


class StateSiteSource:
    """Crawl configured state government sources for MMIP policy links."""

    def __init__(
        self,
        sources_path: str | Path | None = None,
        user_agent: str | None = None,
        per_domain_delay: float = 2.0,
        state_filter: str | None = None,
        source_id_filter: str | None = None,
        include_review_needed: bool = False,
    ):
        self.sources_path = Path(sources_path or os.getenv("STATE_SOURCES_PATH", DEFAULT_SOURCES_PATH))
        self.user_agent = user_agent or os.getenv(
            "CRAWLER_USER_AGENT",
            "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)",
        )
        self.per_domain_delay = per_domain_delay
        self.state_filter = (state_filter or "").strip().upper() or None
        self.source_id_filter = (source_id_filter or "").strip() or None
        self.include_review_needed = include_review_needed
        self.http = HttpFetcher(self.user_agent, per_domain_delay)
        self.browser = BrowserRenderer(self.user_agent)
        self.index_fetcher = IndexFetcher(self.http, self.browser)
        self.search_fetcher = SearchFetcher(self.http, self.browser)
        self.rss_fetcher = RssFetcher(self.http)
        self.api_fetcher = ApiFetcher(self.http)
        self._needs_browser = False

    def load_sources(self) -> list[StateSource]:
        if not self.sources_path.exists():
            logger.warning("State sources file not found: %s", self.sources_path)
            return []
        with open(self.sources_path, encoding="utf-8") as f:
            data = json.load(f)
        return load_sources_data(data)

    def _should_skip(self, source: StateSource) -> bool:
        if self.state_filter and source.state.upper() != self.state_filter:
            return True
        if self.source_id_filter and source.source_id != self.source_id_filter:
            return True
        if source.review_needed and not self.include_review_needed:
            logger.debug("Skipping state source pending review: %s", source.name)
            return True
        return False

    def active_sources(self) -> list[StateSource]:
        return [s for s in self.load_sources() if not self._should_skip(s)]

    def discover(self) -> Iterator[Candidate]:
        active = self.active_sources()
        if not active:
            logger.info("No active state sources to crawl (%s)", self.sources_path)
            return
        progress = get_progress()
        if progress:
            progress.begin_state_crawl(len(active))
        render_js_count = sum(1 for s in active if s.render_js)
        if render_js_count:
            self._needs_browser = True
            if not self.browser.start():
                reason = self.browser._unavailable_reason or "Playwright unavailable"
                logger.warning(
                    "Skipping %d render_js state sources (%s)",
                    render_js_count,
                    reason,
                )
                active = [s for s in active if not s.render_js]
                if not self.browser.available:
                    self._needs_browser = False
        try:
            for idx, source in enumerate(active, start=1):
                if progress:
                    progress.state_source(idx, len(active), source.name)
                logger.info(
                    "Crawling state source %s (%s/%s%s)",
                    source.name,
                    source.method,
                    source.content_type,
                    ", browser" if source.render_js else "",
                )
                fetcher = {
                    "index": self.index_fetcher,
                    "search": self.search_fetcher,
                    "rss": self.rss_fetcher,
                    "api": self.api_fetcher,
                }.get(source.method)
                if not fetcher:
                    logger.warning("Unknown fetch method %s for %s", source.method, source.name)
                    continue
                for candidate in fetcher.discover(source):
                    candidate.source = "state_site"
                    candidate.state = source.state
                    yield candidate
        finally:
            if self._needs_browser:
                self.browser.stop()

    def fetch_page_text(self, url: str) -> tuple[str, str]:
        """Fetch a candidate page for relevance excerpt."""
        from discovery.fetchers import (
            BROWSER_UA,
            extract_document_text,
            fetch_justice_gov_content,
            is_browser_gated_url,
        )

        ua = self.user_agent or BROWSER_UA
        if is_browser_gated_url(url):
            self._needs_browser = True
            body, content_hash, content_type = fetch_justice_gov_content(
                self.http,
                url,
                browser=self.browser,
                user_agent=ua,
            )
        else:
            body, content_hash, content_type = self.http.fetch_content(
                url,
                ignore_robots=True,
                user_agent=ua,
            )
        if not body:
            return "", ""
        text = extract_document_text(body, url, content_type)
        return text[:8000], content_hash
