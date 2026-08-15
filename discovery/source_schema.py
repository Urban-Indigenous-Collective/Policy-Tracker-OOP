"""Schema and helpers for state MMIP crawl source manifests."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator, model_validator

ContentType = Literal[
    "press_release",
    "proclamation",
    "executive_order",
    "letter",
    "legislation",
    "report",
    "other",
]

FetchMethod = Literal["index", "search", "rss", "api"]

Confidence = Literal["high", "medium", "low"]

DEFAULT_SEARCH_QUERIES = [
    "missing and murdered indigenous",
    "missing indigenous",
    "MMIP",
    "MMIW",
    "missing persons indigenous",
    "murdered indigenous",
    "tribal missing persons",
]

# Pages beyond this per index source are not fetched. Five covers roughly five
# years of annual proclamations on a typical governor archive; sites with deep
# histories override it per source.
DEFAULT_MAX_PAGES = 5

# Proclamation and EO archives often paginate one ceremonial document per year;
# depth-5 misses anything older than ~5 years. Per-source overrides (e.g. NC
# procs at 95) still win when set explicitly in manifests.
ARCHIVE_CONTENT_DEFAULT_MAX_PAGES = 15

# Cap opaque-document fetches per index source per run. EO archives can list
# hundreds of PDFs with useless anchor text; without a cap a single source can
# dominate a crawl (NM ~477 PDFs). Zero means unlimited.
DEFAULT_MAX_DOCUMENT_FETCHES = 50

SKIP_DOMAINS = (
    "legiscan.com",
    "congress.gov",
    "justice.gov",
    "federalregister.gov",
)


def slugify_id(state: str, name: str) -> str:
    """Stable source id for CLI filtering."""
    base = f"{state}-{name}".lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base[:80]


class StateSource(BaseModel):
    state: str = Field(..., min_length=2, max_length=2)
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
    # Search method fields
    search_url: str = ""
    search_param: str = "q"
    search_queries: list[str] = Field(default_factory=list)
    http_method: Literal["GET", "POST"] = "GET"
    ssl_verify: bool = True
    ignore_robots: bool = False
    # Some state portals reject the default crawler UA with HTTP 403.
    user_agent: str = ""
    render_js: bool = False
    browser_wait_selector: str = ""
    browser_click_selector: str = ""
    browser_input_selector: str = ""
    browser_submit_selector: str = ""
    # Index pagination. Most archives put one MMIP document per year on
    # successive pages, so page 1 alone sees at most the current year.
    max_pages: int = Field(default=DEFAULT_MAX_PAGES, ge=1, le=500)
    page_url_template: str = ""  # e.g. https://host/proclamations/page/{page}/
    next_page_selector: str = ""  # CSS selector when autodetection fails
    # Opaque PDF / weak-anchor EO listings: max document-body fetches per run.
    max_document_fetches: int = Field(default=DEFAULT_MAX_DOCUMENT_FETCHES, ge=0, le=5000)
    # Hosts other than the listing's own that may hold its documents
    # (e.g. TN EO listings link publications.tnsosfiles.com).
    allowed_extra_domains: list[str] = Field(default_factory=list)
    # RSS method fields
    rss_url: str = ""
    # API method fields (e.g. NY Open Legislation)
    api_url_template: str = ""
    api_key_env: str = ""
    # Optional URL templates with {year} for cheap MMIP awareness-day slug probes
    # (e.g. governor.nc.gov proclamation pages absent from the index).
    year_slug_templates: list[str] = Field(default_factory=list)
    # When an index lists EO numbers in a table without hrefs (e.g. PA pacode),
    # build document URLs by substituting {number} (YYYY-NN) from table rows.
    document_url_template: str = ""
    # Legacy bootstrap fields
    sample_urls: list[str] = Field(default_factory=list)
    occurrence_count: int = 0
    link_selector: str | None = None
    type: str | None = None  # legacy alias for content_type context

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def finalize(self) -> "StateSource":
        if not self.source_id:
            self.source_id = slugify_id(self.state, self.name)
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
            if not self.api_key_env:
                raise ValueError(f"api source '{self.name}' requires api_key_env")
            if not self.search_queries:
                self.search_queries = list(DEFAULT_SEARCH_QUERIES)
        if self.method != "search" and self.search_url and not self.search_url.startswith("http"):
            self.search_url = ""
        if (
            self.content_type in ("proclamation", "executive_order")
            and self.max_pages == DEFAULT_MAX_PAGES
        ):
            self.max_pages = ARCHIVE_CONTENT_DEFAULT_MAX_PAGES
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
        template = self.search_url
        if "{query}" in template:
            return template.replace("{query}", quote(query))
        sep = "&" if "?" in template else "?"
        return f"{template}{sep}{self.search_param}={quote(query)}"


class StateManifest(BaseModel):
    state: str
    sources: list[StateSource] = Field(default_factory=list)

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str) -> str:
        return value.strip().upper()


class StateSourcesFile(BaseModel):
    generated_from: str = "state source manifests"
    note: str = "Set review_needed=false after verifying each crawl target URL"
    sources: list[StateSource] = Field(default_factory=list)


def source_from_legacy(raw: dict[str, Any]) -> StateSource:
    """Upgrade old bootstrap entries to the new schema."""
    method = raw.get("method") or "index"
    return StateSource(
        state=raw.get("state", "XX"),
        name=raw.get("name", "Unknown source"),
        content_type=raw.get("content_type") or raw.get("type") or "other",
        method=method,
        url=raw.get("url", ""),
        review_needed=bool(raw.get("review_needed", True)),
        discovered_by=raw.get("discovered_by", "bootstrap_main_v3"),
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
        rss_url=raw.get("rss_url", ""),
        api_url_template=raw.get("api_url_template", ""),
        api_key_env=raw.get("api_key_env", ""),
        max_pages=int(raw.get("max_pages") or DEFAULT_MAX_PAGES),
        page_url_template=raw.get("page_url_template", ""),
        next_page_selector=raw.get("next_page_selector", ""),
        allowed_extra_domains=raw.get("allowed_extra_domains") or [],
        max_document_fetches=int(raw.get("max_document_fetches") or DEFAULT_MAX_DOCUMENT_FETCHES),
        year_slug_templates=raw.get("year_slug_templates") or [],
        document_url_template=raw.get("document_url_template") or "",
        sample_urls=raw.get("sample_urls") or [],
        occurrence_count=int(raw.get("occurrence_count") or 0),
        link_selector=raw.get("link_selector"),
        type=raw.get("type"),
    )


def load_sources_data(data: dict | list) -> list[StateSource]:
    if isinstance(data, list):
        raws = data
    else:
        raws = data.get("sources", [])
    sources: list[StateSource] = []
    for raw in raws:
        try:
            sources.append(StateSource.model_validate(raw))
        except Exception:
            sources.append(source_from_legacy(raw))
    return sources


def is_blocked_domain(url: str) -> bool:
    lowered = url.lower()
    return any(domain in lowered for domain in SKIP_DOMAINS)
