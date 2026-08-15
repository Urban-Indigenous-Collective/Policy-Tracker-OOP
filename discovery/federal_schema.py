"""Schema and helpers for federal MMIP crawl source manifests."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from discovery.source_schema import (
    DEFAULT_MAX_PAGES,
    DEFAULT_SEARCH_QUERIES,
    Confidence,
    ContentType,
    FetchMethod,
    slugify_id,
)

FEDERAL_STATE = "National"


class FederalSource(BaseModel):
    state: str = FEDERAL_STATE
    name: str = Field(..., min_length=3)
    content_type: ContentType = "other"
    method: FetchMethod = "index"
    url: str = ""
    review_needed: bool = True
    discovered_by: str = "manual"
    discovered_on: str = Field(default_factory=lambda: date.today().isoformat())
    notes: str = ""
    confidence: Confidence = "medium"
    source_id: str = ""
    search_url: str = ""
    search_param: str = "q"
    search_queries: list[str] = Field(default_factory=list)
    http_method: Literal["GET", "POST"] = "GET"
    ssl_verify: bool = True
    ignore_robots: bool = False
    user_agent: str = ""
    render_js: bool = False
    browser_wait_selector: str = ""
    browser_click_selector: str = ""
    browser_input_selector: str = ""
    browser_submit_selector: str = ""
    max_pages: int = Field(default=DEFAULT_MAX_PAGES, ge=1, le=500)
    page_url_template: str = ""
    next_page_selector: str = ""
    allowed_extra_domains: list[str] = Field(default_factory=list)
    rss_url: str = ""
    api_url_template: str = ""
    api_key_env: str = ""
    sample_urls: list[str] = Field(default_factory=list)
    year_slug_templates: list[str] = Field(default_factory=list)
    occurrence_count: int = 0
    link_selector: str | None = None
    office_url: str = ""
    press_url_template: str = ""

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str) -> str:
        return FEDERAL_STATE

    @model_validator(mode="after")
    def finalize(self) -> "FederalSource":
        if not self.source_id:
            self.source_id = slugify_id("fed", self.name)
        if self.method == "search":
            if not self.search_url and self.url:
                self.search_url = self.url
            if not self.search_queries:
                self.search_queries = list(DEFAULT_SEARCH_QUERIES)
        if self.method == "rss" and not self.rss_url and self.url:
            self.rss_url = self.url
        if self.method == "index" and not self.url:
            raise ValueError(f"index source '{self.name}' requires url")
        if self.method == "search" and not self.search_url:
            raise ValueError(f"search source '{self.name}' requires search_url")
        if self.method == "search" and not self.search_url.startswith("http"):
            raise ValueError(f"search source '{self.name}' requires http(s) search_url")
        if self.method == "rss" and not self.rss_url:
            raise ValueError(f"rss source '{self.name}' requires rss_url")
        if self.method == "api":
            if not self.api_url_template and not self.search_url:
                raise ValueError(f"api source '{self.name}' requires api_url_template")
            if not self.search_queries:
                self.search_queries = list(DEFAULT_SEARCH_QUERIES)
        if self.method != "search" and self.search_url and not self.search_url.startswith("http"):
            self.search_url = ""
        if "justice.gov" in (self.url or self.search_url or self.api_url_template).lower():
            if not self.user_agent:
                self.user_agent = (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                )
            if not self.ignore_robots:
                self.ignore_robots = True
            # USAO /pr listings serve page 1 at the bare URL; ?page=N is Akamai-walled.
            if self.method == "index" and "/usao-" in (self.url or "").lower():
                self.max_pages = 1
        return self

    def primary_url(self) -> str:
        if self.method == "rss":
            return self.rss_url
        if self.method == "search":
            return self.search_url
        if self.method == "api":
            return self.api_url_template or self.search_url
        return self.url

    def build_search_url(self, query: str) -> str:
        from urllib.parse import quote

        template = self.search_url
        if "{query}" in template:
            return template.replace("{query}", quote(query))
        sep = "&" if "?" in template else "?"
        return f"{template}{sep}{self.search_param}={quote(query)}"


class FederalManifest(BaseModel):
    sources: list[FederalSource] = Field(default_factory=list)


class FederalSourcesFile(BaseModel):
    generated_from: str = "federal source manifests"
    note: str = "Set review_needed=false after verifying each crawl target URL"
    sources: list[FederalSource] = Field(default_factory=list)


def source_from_legacy(raw: dict[str, Any]) -> FederalSource:
    method = raw.get("method") or "index"
    return FederalSource(
        state=FEDERAL_STATE,
        name=raw.get("name", "Unknown source"),
        content_type=raw.get("content_type") or raw.get("type") or "other",
        method=method,
        url=raw.get("url", ""),
        review_needed=bool(raw.get("review_needed", True)),
        discovered_by=raw.get("discovered_by", "bootstrap_federal"),
        discovered_on=raw.get("discovered_on", date.today().isoformat()),
        notes=raw.get("notes", ""),
        confidence=raw.get("confidence", "medium"),
        source_id=raw.get("source_id", ""),
        search_url=raw.get("search_url", ""),
        search_param=raw.get("search_param", "q"),
        search_queries=raw.get("search_queries") or [],
        http_method=raw.get("http_method", "GET"),
        ssl_verify=bool(raw.get("ssl_verify", True)),
        ignore_robots=bool(raw.get("ignore_robots", False)),
        user_agent=raw.get("user_agent", ""),
        render_js=bool(raw.get("render_js", False)),
        browser_wait_selector=raw.get("browser_wait_selector", ""),
        browser_click_selector=raw.get("browser_click_selector", ""),
        browser_input_selector=raw.get("browser_input_selector", ""),
        browser_submit_selector=raw.get("browser_submit_selector", ""),
        max_pages=int(raw.get("max_pages") or DEFAULT_MAX_PAGES),
        page_url_template=raw.get("page_url_template", ""),
        next_page_selector=raw.get("next_page_selector", ""),
        allowed_extra_domains=raw.get("allowed_extra_domains") or [],
        rss_url=raw.get("rss_url", ""),
        api_url_template=raw.get("api_url_template", ""),
        api_key_env=raw.get("api_key_env", ""),
        sample_urls=raw.get("sample_urls") or [],
        occurrence_count=int(raw.get("occurrence_count") or 0),
        link_selector=raw.get("link_selector"),
        office_url=raw.get("office_url", ""),
        press_url_template=raw.get("press_url_template", ""),
    )


def load_federal_sources_data(data: dict | list) -> list[FederalSource]:
    if isinstance(data, list):
        raws = data
    else:
        raws = data.get("sources", [])
    sources: list[FederalSource] = []
    for raw in raws:
        try:
            sources.append(FederalSource.model_validate(raw))
        except Exception:
            sources.append(source_from_legacy(raw))
    return sources


def is_federal_register_api(url: str) -> bool:
    return "federalregister.gov/api" in url.lower()


_FR_DOCUMENT_ID_RE = re.compile(r"\d{4}-\d{5}")


def is_federal_register_document_url(url: str) -> bool:
    """True for public Federal Register document pages (not API listing URLs)."""
    lower = (url or "").lower()
    return "federalregister.gov/documents/" in lower and bool(_FR_DOCUMENT_ID_RE.search(lower))


def federal_register_document_id(url: str) -> str | None:
    match = _FR_DOCUMENT_ID_RE.search(url or "")
    return match.group(0) if match else None


def is_doj_press_api(url: str) -> bool:
    """Official DOJ News API (press_releases.json) — not HTML listings."""
    lower = (url or "").lower()
    return "justice.gov/api/v1/press_releases" in lower
