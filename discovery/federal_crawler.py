"""Crawl configured federal government sources for MMIP policy links."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterator

from discovery.browser_fetcher import BrowserRenderer
from discovery.fetchers import ApiFetcher, HttpFetcher, IndexFetcher, RssFetcher, SearchFetcher
from discovery.federal_jurisdiction import infer_federal_jurisdiction
from discovery.federal_schema import FederalSource, load_federal_sources_data
from discovery.models import Candidate, utc_now_iso
from discovery.progress import get_progress

logger = logging.getLogger(__name__)

DEFAULT_FEDERAL_SOURCES_PATH = (
    Path(__file__).resolve().parent.parent / "sources" / "federal_sources.json"
)


class FederalSiteSource:
    """Crawl configured federal government sources for MMIP policy links."""

    def __init__(
        self,
        sources_path: str | Path | None = None,
        user_agent: str | None = None,
        per_domain_delay: float = 2.0,
        source_id_filter: str | None = None,
        include_review_needed: bool = False,
    ):
        self.sources_path = Path(
            sources_path or os.getenv("FEDERAL_SOURCES_PATH", DEFAULT_FEDERAL_SOURCES_PATH)
        )
        self.user_agent = user_agent or os.getenv(
            "CRAWLER_USER_AGENT",
            "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)",
        )
        self.per_domain_delay = per_domain_delay
        self.source_id_filter = source_id_filter
        self.include_review_needed = include_review_needed
        self.http = HttpFetcher(self.user_agent, per_domain_delay)
        self.browser = BrowserRenderer(self.user_agent)
        self.index_fetcher = IndexFetcher(self.http, self.browser)
        self.search_fetcher = SearchFetcher(self.http, self.browser)
        self.rss_fetcher = RssFetcher(self.http)
        self.api_fetcher = ApiFetcher(self.http)
        self._needs_browser = False

    def load_sources(self) -> list[FederalSource]:
        if not self.sources_path.exists():
            logger.warning("Federal sources file not found: %s", self.sources_path)
            return []
        with open(self.sources_path, encoding="utf-8") as f:
            data = json.load(f)
        return load_federal_sources_data(data)

    def _should_skip(self, source: FederalSource) -> bool:
        if source.review_needed and not self.include_review_needed:
            logger.debug("Skipping federal source pending review: %s", source.name)
            return True
        if self.source_id_filter and source.source_id != self.source_id_filter:
            return True
        return False

    def discover(self) -> Iterator[Candidate]:
        sources = self.load_sources()
        active = [s for s in sources if not self._should_skip(s)]
        progress = get_progress()
        if progress:
            progress.begin_state_crawl(len(active))
        if any(s.render_js for s in active):
            self._needs_browser = True
        try:
            for idx, source in enumerate(active, start=1):
                if progress:
                    progress.state_source(idx, len(active), source.name)
                logger.info(
                    "Crawling federal source %s (%s/%s%s)",
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
                    candidate.source = "federal_site"
                    candidate.state = infer_federal_jurisdiction(
                        candidate.url,
                        source_id=source.source_id,
                        title=candidate.title,
                        body=candidate.snippet,
                        content_type=source.content_type,
                    )
                    yield candidate
        finally:
            if self._needs_browser:
                self.browser.stop()

    def fetch_page_text(self, url: str) -> tuple[str, str]:
        """Fetch a candidate page for relevance excerpt.

        justice.gov listings/articles are Akamai-gated for plain HTTP (and
        sometimes for headless Chromium). Prefer a browser-like UA, then
        Playwright when HTTP returns a bot wall.

        federalregister.gov HTML pages are bot-gated; use the developer API.
        """
        from discovery.fetchers import (
            BROWSER_UA,
            extract_document_text,
            fetch_federal_register_document_text,
            fetch_justice_gov_content,
            is_federal_register_document_url,
            is_justice_gov_url,
        )

        if is_federal_register_document_url(url):
            text, content_hash = fetch_federal_register_document_text(self.http, url)
            if text:
                return text[:8000], content_hash

        ua = BROWSER_UA if is_justice_gov_url(url) else (self.user_agent or BROWSER_UA)
        if is_justice_gov_url(url):
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
