import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from discovery.models import Candidate, utc_now_iso
from discovery.queries import keyword_prescreen

logger = logging.getLogger(__name__)

DEFAULT_SOURCES_PATH = Path(__file__).resolve().parent.parent / "sources" / "state_sources.json"


class StateSiteSource:
    """Crawl configured state government index pages for MMIP policy links."""

    def __init__(
        self,
        sources_path: str | Path | None = None,
        user_agent: str | None = None,
        per_domain_delay: float = 2.0,
    ):
        self.sources_path = Path(sources_path or os.getenv("STATE_SOURCES_PATH", DEFAULT_SOURCES_PATH))
        self.user_agent = user_agent or os.getenv(
            "CRAWLER_USER_AGENT",
            "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)",
        )
        self.per_domain_delay = per_domain_delay
        self._robots_cache: dict[str, RobotFileParser] = {}
        self._last_fetch: dict[str, float] = {}
        self._page_hashes: dict[str, str] = {}

    def load_sources(self) -> list[dict]:
        if not self.sources_path.exists():
            logger.warning("State sources file not found: %s", self.sources_path)
            return []
        with open(self.sources_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("sources", [])
        return data

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def _can_fetch(self, url: str) -> bool:
        domain = self._domain(url)
        if domain not in self._robots_cache:
            rp = RobotFileParser()
            robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
            rp.set_url(robots_url)
            try:
                rp.read()
            except Exception:
                logger.debug("Could not read robots.txt for %s, allowing fetch", domain)
                rp = None
            self._robots_cache[domain] = rp
        rp = self._robots_cache[domain]
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    def _rate_limit(self, domain: str) -> None:
        last = self._last_fetch.get(domain, 0)
        elapsed = time.time() - last
        if elapsed < self.per_domain_delay:
            time.sleep(self.per_domain_delay - elapsed)
        self._last_fetch[domain] = time.time()

    def _fetch(self, url: str) -> tuple[str, str]:
        domain = self._domain(url)
        if not self._can_fetch(url):
            logger.info("Robots.txt disallows fetch: %s", url)
            return "", ""
        self._rate_limit(domain)
        headers = {"User-Agent": self.user_agent}
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            content_hash = hashlib.sha256(response.content).hexdigest()
            return response.text, content_hash
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return "", ""

    def _extract_links(self, base_url: str, html: str) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        base_domain = self._domain(base_url)
        links: list[tuple[str, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue
            absolute = urljoin(base_url, href)
            if self._domain(absolute) != base_domain:
                continue
            text = anchor.get_text(" ", strip=True)
            if text:
                links.append((absolute, text))
        return links

    def discover(self) -> Iterator[Candidate]:
        sources = self.load_sources()
        for source in sources:
            if source.get("review_needed"):
                logger.debug("Skipping source pending review: %s", source.get("name"))
                continue
            index_url = source.get("url", "")
            state = source.get("state", "")
            if not index_url:
                continue

            html, content_hash = self._fetch(index_url)
            if not html:
                continue

            prev_hash = self._page_hashes.get(index_url)
            self._page_hashes[index_url] = content_hash
            if prev_hash and prev_hash == content_hash:
                logger.debug("Index unchanged, checking links only: %s", index_url)

            for link_url, link_text in self._extract_links(index_url, html):
                combined = f"{link_text}\n{index_url}"
                if not keyword_prescreen(combined):
                    continue
                yield Candidate(
                    source="state_site",
                    state=state,
                    url=link_url,
                    title=link_text,
                    snippet=link_text,
                    content_hash=content_hash,
                    discovered_at=utc_now_iso(),
                )

    def fetch_page_text(self, url: str) -> tuple[str, str]:
        """Fetch a candidate page for relevance excerpt."""
        html, content_hash = self._fetch(url)
        if not html:
            return "", ""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        return text[:8000], content_hash
