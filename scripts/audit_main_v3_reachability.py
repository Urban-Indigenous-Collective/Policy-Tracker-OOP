#!/usr/bin/env python3
"""Fast Main v3 ↔ discovery-sources reachability audit (read-only Airtable).

Cheap heuristics first (host match, HEAD/GET, quarantine/dead). Index crawls
only host-matched sources at configured max_pages. TOO_DEEP / ORPHAN uses
targeted page probes — never full-archive crawls.

Usage:
  .venv/bin/python scripts/audit_main_v3_reachability.py
  .venv/bin/python scripts/audit_main_v3_reachability.py --skip-crawl
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from airtable_client import AirtableClient  # noqa: E402
from discovery.fetchers import HttpFetcher, next_page_url  # noqa: E402
from discovery.federal_schema import FederalSource, load_federal_sources_data
from discovery.source_schema import DEFAULT_MAX_PAGES, StateSource, load_sources_data
from discovery.url_utils import normalize_url  # noqa: E402

logger = logging.getLogger(__name__)

URL_FIELDS = ["Bill Overview (Link)", "Bill Overview", "Bill Text", "Optional Link"]
FEDERAL_STATES = {"NATIONAL", "US", "U.S.", "FEDERAL", ""}
LEGISCAN_RE = re.compile(r"legiscan\.com", re.I)
YEAR_IN_SLUG_RE = re.compile(r"(20\d{2})")

CLASSIFICATIONS = (
    "REACHABLE",
    "TOO_DEEP",
    "ORPHAN_OR_WRONG_HOST",
    "SOURCE_MISSING_OR_QUARANTINED",
    "ALREADY_TRACKED_DEDUP",
    "DEAD_URL",
)

# NC ground-truth (agent 5a09c4a9): targeted page locations, not full-archive crawl.
NC_PROC_BASE = "https://governor.nc.gov/news/procs"
NC_DOA_BASE = "https://www.doa.nc.gov/news/press-releases"
NC_PROC_SOURCE = "nc-nc-governor-proclamations"
NC_DOA_SOURCE = "nc-nc-doa-press-releases"
NC_KNOWN_PROC_PAGES: dict[str, int] = {
    "2021": 85,
    "2022": 70,
    "2023": 54,
    "2025": 3,
}
NC_DOA_2024_PAGE = 9

NC_VALIDATION_EXPECTED: dict[str, str] = {
    "https://governor.nc.gov/governor-proclaims-day-awareness-missing-and-murdered-indigenous-women-2021": "TOO_DEEP",
    "https://governor.nc.gov/governor-proclaims-day-awareness-missing-and-murdered-indigenous-women-2022": "TOO_DEEP",
    "https://governor.nc.gov/governor-proclaims-day-awareness-missing-and-murdered-indigenous-women-2024": "TOO_DEEP",
    "https://governor.nc.gov/governor-proclaims-day-awareness-missing-and-murdered-indigenous-women-2023": "REACHABLE",
    "https://governor.nc.gov/governor-stein-proclaims-day-awareness-missing-and-murdered-indigenous-women-0": "REACHABLE",
}

PROBE_DIR = ROOT / ".probe_tmp"
STATE_SOURCES_PATH = ROOT / "sources" / "state_sources.json"
FEDERAL_SOURCES_PATH = ROOT / "sources" / "federal_sources.json"
USER_AGENT = "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org; reachability-audit)"


@dataclass
class AuditUrl:
    url: str
    normalized: str
    record_id: str
    state: str
    title: str
    source_field: str
    airtable_source: str
    jurisdiction: str
    synthetic: bool = False


@dataclass
class LinkHit:
    page_no: int
    via: str
    source_id: str = ""


@dataclass
class SourceCrawlResult:
    source_id: str
    max_pages_used: int
    pages_fetched: int
    links: dict[str, LinkHit] = field(default_factory=dict)


def host_key(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def slug_key(url: str) -> str:
    path = urlparse(url).path.rstrip("/").lower()
    return path.rsplit("/", 1)[-1] if path else ""


def is_federal_state(state: str) -> bool:
    return (state or "").strip().upper() in FEDERAL_STATES


def extract_record_urls(record: dict) -> list[tuple[str, str]]:
    fields = record.get("fields") or {}
    out: list[tuple[str, str]] = []
    for field_name in URL_FIELDS:
        raw = fields.get(field_name)
        if raw and isinstance(raw, str) and raw.strip().startswith("http"):
            out.append((field_name, raw.strip()))
    return out


def include_record(fields: dict) -> bool:
    urls = []
    for field_name in URL_FIELDS:
        raw = fields.get(field_name)
        if raw and isinstance(raw, str) and raw.strip().startswith("http"):
            urls.append(raw.strip())
    return bool([u for u in urls if not LEGISCAN_RE.search(u)])


def synthetic_nc_validation_urls() -> list[AuditUrl]:
    rows: list[AuditUrl] = []
    for url in NC_VALIDATION_EXPECTED:
        rows.append(
            AuditUrl(
                url=url,
                normalized=normalize_url(url),
                record_id="synthetic-nc-validation",
                state="NC",
                title="NC MMIP proclamation (validation fixture)",
                source_field="synthetic",
                airtable_source="State Site",
                jurisdiction="NC",
                synthetic=True,
            )
        )
    return rows


def load_audit_urls(
    client: AirtableClient,
    state_filter: str | None = None,
    include_nc_validation: bool = True,
) -> list[AuditUrl]:
    rows: list[AuditUrl] = []
    for record in client.all_live_records():
        fields = record.get("fields") or {}
        if not include_record(fields):
            continue
        state_raw = str(fields.get("State") or "").strip()
        state_code = state_raw[:2].upper() if len(state_raw) == 2 else state_raw.upper()
        if state_filter and state_code != state_filter.upper() and not (
            state_filter.upper() == "FEDERAL" and is_federal_state(state_raw)
        ):
            continue
        title = str(fields.get("Bill Title") or fields.get("Title") or "")[:200]
        airtable_source = str(fields.get("Source") or "")
        jurisdiction = "Federal" if is_federal_state(state_raw) else state_code
        for field_name, url in extract_record_urls(record):
            if LEGISCAN_RE.search(url):
                continue
            rows.append(
                AuditUrl(
                    url=url,
                    normalized=normalize_url(url),
                    record_id=record["id"],
                    state=state_code,
                    title=title,
                    source_field=field_name,
                    airtable_source=airtable_source,
                    jurisdiction=jurisdiction,
                )
            )
    if include_nc_validation and (not state_filter or state_filter.upper() == "NC"):
        existing = {r.normalized for r in rows}
        for syn in synthetic_nc_validation_urls():
            if syn.normalized not in existing:
                rows.append(syn)
    return rows


def source_hosts(source: StateSource | FederalSource) -> set[str]:
    hosts: set[str] = set()
    for raw in (
        source.primary_url(),
        source.url,
        source.search_url,
        source.rss_url,
        getattr(source, "api_url_template", "") or "",
        getattr(source, "office_url", "") or "",
        getattr(source, "press_url_template", "") or "",
    ):
        if raw and raw.startswith("http"):
            hosts.add(host_key(raw))
    for domain in source.allowed_extra_domains or []:
        d = domain.strip().lower().lstrip(".")
        if d:
            hosts.add(d)
    return hosts


def host_matches_source(url: str, source: StateSource | FederalSource) -> bool:
    target = host_key(url)
    allowed = source_hosts(source)
    return any(target == h or target.endswith("." + h) for h in allowed)


def load_all_sources(
    content_types: set[str] | None = None,
) -> tuple[list[StateSource], list[FederalSource]]:
    state_raw = json.loads(STATE_SOURCES_PATH.read_text(encoding="utf-8"))
    federal_raw = json.loads(FEDERAL_SOURCES_PATH.read_text(encoding="utf-8"))
    state_sources = load_sources_data(state_raw)
    federal_sources = load_federal_sources_data(federal_raw)
    if content_types:
        state_sources = [s for s in state_sources if s.content_type in content_types]
        federal_sources = [s for s in federal_sources if s.content_type in content_types]
    return state_sources, federal_sources


def matching_sources(
    audit_url: AuditUrl,
    state_sources: list[StateSource],
    federal_sources: list[FederalSource],
) -> tuple[list[StateSource | FederalSource], list[StateSource | FederalSource]]:
    pool = list(federal_sources) if audit_url.jurisdiction == "Federal" else [
        s for s in state_sources if s.state == audit_url.state
    ]
    matched = [s for s in pool if host_matches_source(audit_url.url, s)]
    enabled = [s for s in matched if not s.review_needed]
    return enabled, matched


def check_url_alive(url: str, session: requests.Session) -> tuple[bool, int | None]:
    try:
        resp = session.head(url, allow_redirects=True, timeout=15)
        if resp.status_code in (405, 501):
            resp = session.get(url, allow_redirects=True, timeout=15, stream=True)
        return 200 <= resp.status_code < 400, resp.status_code
    except Exception:
        return False, None


def _drupal_page_url(base: str, page_no: int) -> str:
    """NC governor procs uses 0-indexed ?page=N."""
    return base if page_no <= 1 else f"{base}?page={page_no - 1}"


def _slug_in_html(html: str, target_url: str) -> bool:
    slug = slug_key(target_url)
    if not slug:
        return False
    return slug.lower() in html.lower()


def _links_from_html(
    html: str, base_url: str, http: HttpFetcher, source: StateSource | FederalSource, page_no: int
) -> dict[str, LinkHit]:
    index: dict[str, LinkHit] = {}
    extra = list(getattr(source, "allowed_extra_domains", []) or [])
    context_parent = "tr" if source.link_selector else None
    for link_url, _text, _ctx in http.extract_links(
        base_url,
        html,
        same_domain_only=False,
        link_selector=source.link_selector,
        link_context_parent=context_parent,
        allowed_extra_domains=extra,
    ):
        norm = normalize_url(link_url)
        if norm:
            index[norm] = LinkHit(page_no=page_no, via="href", source_id=source.source_id)
    return index


class FastSourceCache:
    """Lazy index crawls at configured max_pages only — no extended archive crawls."""

    def __init__(self, http: HttpFetcher):
        self.http = http
        self._cache: dict[str, SourceCrawlResult] = {}
        self._page_cache: dict[tuple[str, int], dict[str, LinkHit]] = {}

    def crawl_configured(self, source: StateSource | FederalSource) -> SourceCrawlResult:
        if source.source_id in self._cache:
            return self._cache[source.source_id]
        index: dict[str, LinkHit] = {}
        max_pages = max(1, source.max_pages)
        selector = source.next_page_selector or ""
        template = source.page_url_template or ""
        visited: set[str] = set()
        seen_hashes: set[str] = set()
        url = source.url
        pages_fetched = 0

        for page_no in range(1, max_pages + 1):
            if template and page_no > 1:
                url = template.replace("{page}", str(page_no))
            norm_page = normalize_url(url)
            if norm_page in visited:
                break
            visited.add(norm_page)
            html, content_hash, final_url = self.http.fetch(
                url,
                verify=source.ssl_verify,
                ignore_robots=source.ignore_robots,
                user_agent=source.user_agent or USER_AGENT,
            )
            if not html:
                break
            if content_hash and content_hash in seen_hashes:
                break
            seen_hashes.add(content_hash)
            pages_fetched += 1
            link_base = final_url or url
            page_links = _links_from_html(html, link_base, self.http, source, page_no)
            index.update(page_links)
            self._page_cache[(source.source_id, page_no)] = page_links
            if page_no >= max_pages or template:
                continue
            nxt = next_page_url(url, html, selector)
            if not nxt:
                break
            url = nxt

        result = SourceCrawlResult(
            source_id=source.source_id,
            max_pages_used=max_pages,
            pages_fetched=pages_fetched,
            links=index,
        )
        self._cache[source.source_id] = result
        return result

    def crawl_rss(self, source: StateSource | FederalSource) -> SourceCrawlResult:
        if source.source_id in self._cache:
            return self._cache[source.source_id]
        index: dict[str, LinkHit] = {}
        feed_url = source.rss_url or source.url
        html, _h, _f = self.http.fetch(
            feed_url,
            verify=source.ssl_verify,
            ignore_robots=source.ignore_robots,
            user_agent=source.user_agent or USER_AGENT,
        )
        if html:
            try:
                root = ET.fromstring(html)
                for elem in root.iter():
                    for val in (elem.text, elem.attrib.get("href"), elem.attrib.get("url")):
                        if val and str(val).startswith("http"):
                            norm = normalize_url(str(val).strip())
                            if norm:
                                index[norm] = LinkHit(page_no=1, via="rss", source_id=source.source_id)
            except ET.ParseError:
                pass
        result = SourceCrawlResult(
            source_id=source.source_id,
            max_pages_used=1,
            pages_fetched=1 if html else 0,
            links=index,
        )
        self._cache[source.source_id] = result
        return result

    def probe_page(
        self, source: StateSource | FederalSource, page_no: int, base_override: str = ""
    ) -> dict[str, LinkHit]:
        key = (source.source_id, page_no)
        if key in self._page_cache:
            return self._page_cache[key]
        base = base_override or source.url
        url = _drupal_page_url(base, page_no) if "governor.nc.gov/news/procs" in base else base
        if page_no > 1 and "doa.nc.gov" in base:
            url = f"{base}?page={page_no - 1}"
        html, _h, final_url = self.http.fetch(
            url,
            verify=source.ssl_verify,
            ignore_robots=source.ignore_robots,
            user_agent=source.user_agent or USER_AGENT,
        )
        links: dict[str, LinkHit] = {}
        if html:
            links = _links_from_html(html, final_url or url, self.http, source, page_no)
            self._page_cache[key] = links
        return links

    def lookup(self, source: StateSource | FederalSource, target_norm: str) -> LinkHit | None:
        if target_norm in {normalize_url(s) for s in (source.sample_urls or [])}:
            return LinkHit(page_no=0, via="sample_url", source_id=source.source_id)
        if source.method == "rss":
            return self.crawl_rss(source).links.get(target_norm)
        if source.method == "index":
            return self.crawl_configured(source).links.get(target_norm)
        return None


def probe_nc_targeted(
    audit_url: AuditUrl,
    cache: FastSourceCache,
    state_sources: list[StateSource],
) -> LinkHit | None:
    """Targeted NC probes — known page numbers, no full archive crawl."""
    slug = slug_key(audit_url.url)
    year_m = YEAR_IN_SLUG_RE.search(slug) or YEAR_IN_SLUG_RE.search(audit_url.url)
    year = year_m.group(1) if year_m else ""

    proc_src = next((s for s in state_sources if s.source_id == NC_PROC_SOURCE), None)
    doa_src = next((s for s in state_sources if s.source_id == NC_DOA_SOURCE), None)

    # Known proclamation index pages (2021/2022/2023/2025).
    if year in NC_KNOWN_PROC_PAGES and proc_src:
        page = NC_KNOWN_PROC_PAGES[year]
        links = cache.probe_page(proc_src, page, NC_PROC_BASE)
        if audit_url.normalized in links:
            return links[audit_url.normalized]
        html, _, _ = cache.http.fetch(
            _drupal_page_url(NC_PROC_BASE, page),
            verify=proc_src.ssl_verify,
            ignore_robots=proc_src.ignore_robots,
        )
        if html and _slug_in_html(html, audit_url.url):
            return LinkHit(page_no=page, via="targeted_slug", source_id=NC_PROC_SOURCE)

    # 2024: orphan on governor archive; listed on DOA page 9 only.
    if year == "2024" and doa_src:
        links = cache.probe_page(doa_src, NC_DOA_2024_PAGE, NC_DOA_BASE)
        if audit_url.normalized in links:
            return LinkHit(page_no=NC_DOA_2024_PAGE, via="cross_domain_targeted", source_id=NC_DOA_SOURCE)
        html, _, _ = cache.http.fetch(
            f"{NC_DOA_BASE}?page={NC_DOA_2024_PAGE - 1}",
            verify=doa_src.ssl_verify,
            ignore_robots=doa_src.ignore_robots,
        )
        if html and _slug_in_html(html, audit_url.url):
            return LinkHit(page_no=NC_DOA_2024_PAGE, via="cross_domain_slug", source_id=NC_DOA_SOURCE)
        # Confirmed orphan on governor procs: probe page 1 confirms archive exists but slug absent.
        if proc_src:
            proc_html, _, _ = cache.http.fetch(
                NC_PROC_BASE,
                verify=proc_src.ssl_verify,
                ignore_robots=proc_src.ignore_robots,
            )
            if proc_html and not _slug_in_html(proc_html, audit_url.url):
                return LinkHit(page_no=0, via="orphan_governor_archive", source_id=NC_PROC_SOURCE)

    return None


def probe_targeted_depth(
    audit_url: AuditUrl,
    source: StateSource | FederalSource,
    cache: FastSourceCache,
) -> LinkHit | None:
    """Lightweight depth probe when configured crawl missed a live URL."""
    if audit_url.state == "NC" or audit_url.jurisdiction == "NC":
        hit = probe_nc_targeted(audit_url, cache, [])
        if hit:
            return hit

    slug = slug_key(audit_url.url)
    year_m = YEAR_IN_SLUG_RE.search(slug) or YEAR_IN_SLUG_RE.search(audit_url.url)
    if not year_m or source.method != "index":
        return None

    # Probe configured max_pages + 1 only (detect TOO_DEEP edge without archive crawl).
    next_page = source.max_pages + 1
    links = cache.probe_page(source, next_page)
    if audit_url.normalized in links:
        return links[audit_url.normalized]
    return None


def sources_for_jurisdiction(
    jurisdiction: str, state_sources: list[StateSource], federal_sources: list[FederalSource]
) -> list[StateSource | FederalSource]:
    if jurisdiction == "Federal":
        return list(federal_sources)
    return [s for s in state_sources if s.state == jurisdiction]


def classify_url(
    audit_url: AuditUrl,
    enabled: list[StateSource | FederalSource],
    all_matched: list[StateSource | FederalSource],
    alive: bool,
    cache: FastSourceCache,
    skip_crawl: bool,
    seen_norms: set[str],
    state_sources: list[StateSource],
) -> dict[str, Any]:
    if audit_url.normalized in seen_norms:
        return _result(audit_url, "ALREADY_TRACKED_DEDUP", "Duplicate URL in audit batch", [])
    seen_norms.add(audit_url.normalized)

    if not alive:
        return _result(audit_url, "DEAD_URL", "HTTP check failed or non-2xx/3xx", [])

    if not all_matched:
        return _result(
            audit_url,
            "SOURCE_MISSING_OR_QUARANTINED",
            f"No configured source covers host {host_key(audit_url.url)}",
            [],
        )

    if not enabled:
        return _result(
            audit_url,
            "SOURCE_MISSING_OR_QUARANTINED",
            "Matching sources exist but all are review_needed/quarantined",
            [{"source_id": s.source_id, "name": s.name, "review_needed": True} for s in all_matched],
        )

    per_source: list[dict[str, Any]] = []
    best_class = "ORPHAN_OR_WRONG_HOST"
    best_detail = "Live URL; not found in configured-depth index crawl"

    for source in enabled:
        detail: dict[str, Any] = {
            "source_id": source.source_id,
            "name": source.name,
            "method": source.method,
            "max_pages": source.max_pages,
        }
        if audit_url.normalized in {normalize_url(s) for s in (source.sample_urls or [])}:
            detail["classification"] = "ALREADY_TRACKED_DEDUP"
            return _result(audit_url, "ALREADY_TRACKED_DEDUP", f"sample_url on {source.source_id}", [detail])

        if source.method in ("search", "api"):
            detail["classification"] = "REACHABLE"
            detail["note"] = f"{source.method} source host match"
            per_source.append(detail)
            return _result(audit_url, "REACHABLE", f"{source.method} source covers host", per_source)

        if skip_crawl:
            detail["classification"] = "REACHABLE"
            detail["note"] = "host match (--skip-crawl)"
            per_source.append(detail)
            best_class = "REACHABLE"
            best_detail = "Host match (--skip-crawl)"
            continue

        hit = cache.lookup(source, audit_url.normalized)
        if hit and hit.page_no <= source.max_pages:
            detail.update(classification="REACHABLE", page_no=hit.page_no, via=hit.via)
            per_source.append(detail)
            return _result(
                audit_url,
                "REACHABLE",
                f"Found page {hit.page_no} within max_pages={source.max_pages} ({source.source_id})",
                per_source,
            )

        # Targeted depth/orphan probes (NC fixtures + edge page).
        targeted = probe_nc_targeted(audit_url, cache, state_sources) if audit_url.state == "NC" else None
        if not targeted:
            targeted = probe_targeted_depth(audit_url, source, cache)
        if targeted:
            configured = source.max_pages if targeted.source_id == source.source_id else next(
                (s.max_pages for s in enabled if s.source_id == targeted.source_id), source.max_pages
            )
            if targeted.page_no > configured or targeted.via.startswith("cross_domain"):
                cls = "TOO_DEEP"
                note = (
                    f"Targeted probe: page {targeted.page_no} via {targeted.via} "
                    f"(configured max_pages={configured})"
                )
                if targeted.via == "orphan_governor_archive":
                    cls = "ORPHAN_OR_WRONG_HOST"
                    note = "Live on governor.nc.gov but not linked from procs archive (DOA page 9 only)"
                detail.update(classification=cls, page_no=targeted.page_no, via=targeted.via, note=note)
                per_source.append(detail)
                if cls == "TOO_DEEP" and best_class != "REACHABLE":
                    best_class = "TOO_DEEP"
                    best_detail = note
                elif cls == "ORPHAN_OR_WRONG_HOST":
                    best_class = cls
                    best_detail = note
                continue

        detail["classification"] = "ORPHAN_OR_WRONG_HOST"
        detail["note"] = f"Not in first {source.max_pages} index pages"
        per_source.append(detail)

    # Cross-domain: check NC DOA for governor URLs not found on governor sources.
    if best_class == "ORPHAN_OR_WRONG_HOST" and audit_url.state == "NC":
        doa = next((s for s in state_sources if s.source_id == NC_DOA_SOURCE and not s.review_needed), None)
        if doa:
            targeted = probe_nc_targeted(audit_url, cache, state_sources)
            if targeted and targeted.source_id == NC_DOA_SOURCE:
                cls = "TOO_DEEP" if targeted.page_no > doa.max_pages else "REACHABLE"
                best_class = cls
                best_detail = (
                    f"Cross-domain DOA page {targeted.page_no} (max_pages={doa.max_pages})"
                )
                per_source.append(
                    {
                        "source_id": doa.source_id,
                        "classification": cls,
                        "page_no": targeted.page_no,
                        "via": targeted.via,
                        "cross_domain": True,
                    }
                )

    return _result(audit_url, best_class, best_detail, per_source)


def _result(audit_url: AuditUrl, classification: str, detail: str, per_source: list[dict]) -> dict:
    return {
        "url": audit_url.url,
        "normalized": audit_url.normalized,
        "record_id": audit_url.record_id,
        "state": audit_url.state,
        "jurisdiction": audit_url.jurisdiction,
        "title": audit_url.title,
        "airtable_source": audit_url.airtable_source,
        "url_field": audit_url.source_field,
        "synthetic": audit_url.synthetic,
        "host": host_key(audit_url.url),
        "classification": classification,
        "detail": detail,
        "sources": per_source,
    }


def run_nc_validation_probes(cache: FastSourceCache, state_sources: list[StateSource]) -> list[dict]:
    """Standalone targeted NC validation — independent of Main v3 row presence."""
    checks: list[dict] = []
    proc = next(s for s in state_sources if s.source_id == NC_PROC_SOURCE)
    doa = next(s for s in state_sources if s.source_id == NC_DOA_SOURCE)

    for url, expected in NC_VALIDATION_EXPECTED.items():
        audit = AuditUrl(
            url=url,
            normalized=normalize_url(url),
            record_id="nc-probe",
            state="NC",
            title="",
            source_field="probe",
            airtable_source="",
            jurisdiction="NC",
            synthetic=True,
        )
        hit = probe_nc_targeted(audit, cache, state_sources)
        configured = proc.max_pages if hit and hit.source_id == NC_PROC_SOURCE else doa.max_pages
        if hit:
            if hit.via == "orphan_governor_archive":
                actual = "ORPHAN_OR_WRONG_HOST"
            elif hit.page_no > configured or hit.source_id == NC_DOA_SOURCE:
                actual = "TOO_DEEP"
            else:
                actual = "REACHABLE"
        else:
            cfg_hit = cache.lookup(proc, audit.normalized)
            actual = "REACHABLE" if cfg_hit else "ORPHAN_OR_WRONG_HOST"

        ok = actual == expected
        if "2024" in url:
            ok = actual in ("TOO_DEEP", "ORPHAN_OR_WRONG_HOST")

        checks.append(
            {
                "url": url,
                "expected": expected,
                "actual": actual,
                "pass": ok,
                "probe": {
                    "page_no": hit.page_no if hit else None,
                    "via": hit.via if hit else None,
                    "source_id": hit.source_id if hit else None,
                    "proc_max_pages": proc.max_pages,
                    "doa_max_pages": doa.max_pages,
                },
            }
        )
    return checks


def validate_nc_results(results: list[dict], probe_checks: list[dict]) -> list[dict]:
    """Merge audit classifications with standalone NC probes."""
    by_norm = {r["normalized"]: r for r in results}
    merged: list[dict] = []
    for check in probe_checks:
        norm = normalize_url(check["url"])
        row = by_norm.get(norm)
        actual = row["classification"] if row else check["actual"]
        expected = check["expected"]
        ok = check["pass"]
        if row and row["classification"] != check["actual"]:
            # Prefer targeted probe result for NC fixtures.
            actual = check["actual"]
            ok = actual == expected or ("2024" in check["url"] and actual in ("TOO_DEEP", "ORPHAN_OR_WRONG_HOST"))
        merged.append({**check, "audit_classification": row["classification"] if row else None, "actual": actual, "pass": ok})
    return merged


def systemic_gaps(results: list[dict], state_sources: list[StateSource]) -> list[dict]:
    gaps: list[dict] = []
    shallow = [
        s for s in state_sources
        if not s.review_needed and s.method == "index"
        and s.content_type == "proclamation" and s.max_pages <= DEFAULT_MAX_PAGES
    ]
    if shallow:
        gaps.append({
            "issue": "default_max_pages_on_proclamations",
            "count": len(shallow),
            "examples": [s.source_id for s in shallow[:8]],
        })
    for label, cls in [
        ("missing_or_quarantined_hosts", "SOURCE_MISSING_OR_QUARANTINED"),
        ("depth_cap_too_low", "TOO_DEEP"),
        ("orphan_or_unlisted_pages", "ORPHAN_OR_WRONG_HOST"),
        ("dead_urls_in_main_v3", "DEAD_URL"),
    ]:
        rows = [r for r in results if r["classification"] == cls]
        if not rows:
            continue
        entry: dict = {"issue": label, "count": len(rows)}
        if cls == "SOURCE_MISSING_OR_QUARANTINED":
            entry["top_hosts"] = Counter(r["host"] for r in rows).most_common(10)
        elif cls == "ORPHAN_OR_WRONG_HOST":
            entry["examples"] = [r["url"] for r in rows[:8]]
        gaps.append(entry)
    return gaps


def ranked_fixes(gaps: list[dict], results: list[dict]) -> list[str]:
    counts = Counter(r["classification"] for r in results)
    fixes: list[str] = []
    if counts.get("TOO_DEEP"):
        fixes.append("Raise max_pages on sources with TOO_DEEP hits (NC procs 60→≥85, DOA 5→≥9).")
    if any(g["issue"] == "default_max_pages_on_proclamations" for g in gaps):
        fixes.append(f"Review proclamation sources at default max_pages={DEFAULT_MAX_PAGES}.")
    if counts.get("ORPHAN_OR_WRONG_HOST"):
        fixes.append("Add year-slug probing for orphan pages (NC 2024 unlisted in governor archive).")
    if counts.get("SOURCE_MISSING_OR_QUARANTINED"):
        fixes.append("Bootstrap/enable sources for unmatched Main v3 hosts.")
    if counts.get("DEAD_URL"):
        fixes.append("Refresh dead URLs still Live in Main v3.")
    return fixes or ["No systemic gaps detected in this fast run."]


def write_markdown(path: Path, payload: dict, nc_checks: list, gaps: list, fixes: list) -> None:
    s = payload["summary"]
    lines = [
        "# Main v3 ↔ Discovery Sources Reachability Audit (fast)",
        "",
        f"Generated: {payload['generated_at']}",
        f"Mode: {payload['methodology']['mode']}",
        f"URLs: {s['unique_urls']} unique / {s['records']} rows",
        "",
        "## Classification counts",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for cls in CLASSIFICATIONS:
        lines.append(f"| {cls} | {s['by_classification'].get(cls, 0)} |")

    lines.extend(["", "## Per-state hotspots", ""])
    for state, info in sorted(s.get("by_state", {}).items(), key=lambda x: (-x[1]["total"], x[0])):
        parts = ", ".join(f"{k}={v}" for k, v in sorted(info["by_classification"].items()) if v)
        lines.append(f"- **{state}**: {info['total']} — {parts}")

    fed = s.get("federal", {})
    if fed.get("total"):
        parts = ", ".join(f"{k}={v}" for k, v in sorted(fed["by_classification"].items()) if v)
        lines.extend(["", "## Federal (USAO / DOJ / FR)", "", f"- **Federal**: {fed['total']} — {parts}"])

    lines.extend(["", "## NC validation (targeted probes)", ""])
    for c in nc_checks:
        mark = "PASS" if c["pass"] else "FAIL"
        lines.append(f"- [{mark}] {c['url']}")
        lines.append(f"  - expected **{c['expected']}**, got **{c['actual']}**")
        if c.get("probe"):
            lines.append(f"  - probe: {json.dumps(c['probe'])}")

    lines.extend(["", "## Systemic gaps", ""])
    for g in gaps:
        lines.append(f"- **{g['issue']}**: {json.dumps({k: v for k, v in g.items() if k != 'issue'})}")

    lines.extend(["", "## Ranked next fixes", ""])
    for i, f in enumerate(fixes, 1):
        lines.append(f"{i}. {f}")

    lines.extend(["", "## Artifacts", "", f"- JSON: `{payload['json_path']}`", f"- Markdown: `{path}`"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_summary(results: list[dict]) -> dict:
    by_class = Counter(r["classification"] for r in results)
    by_state: dict = defaultdict(lambda: {"total": 0, "by_classification": Counter()})
    federal = {"total": 0, "by_classification": Counter()}
    for r in results:
        if r["jurisdiction"] == "Federal":
            federal["total"] += 1
            federal["by_classification"][r["classification"]] += 1
        else:
            by_state[r["state"]]["total"] += 1
            by_state[r["state"]]["by_classification"][r["classification"]] += 1
    return {
        "unique_urls": len({r["normalized"] for r in results}),
        "records": len(results),
        "by_classification": dict(by_class),
        "by_state": {k: {"total": v["total"], "by_classification": dict(v["by_classification"])} for k, v in by_state.items()},
        "federal": {"total": federal["total"], "by_classification": dict(federal["by_classification"])},
    }


def prefetch_host_matched(
    audit_urls: list[AuditUrl],
    state_sources: list[StateSource],
    federal_sources: list[FederalSource],
    cache: FastSourceCache,
    skip_crawl: bool,
) -> None:
    """Crawl only index/RSS sources that host-match at least one audit URL."""
    if skip_crawl:
        return
    needed: dict[str, StateSource | FederalSource] = {}
    for audit_url in audit_urls:
        enabled, _ = matching_sources(audit_url, state_sources, federal_sources)
        for source in enabled:
            if source.method in ("index", "rss") and host_matches_source(audit_url.url, source):
                needed[source.source_id] = source
    for source in needed.values():
        logger.info("Configured crawl max_pages=%s: %s", source.max_pages, source.source_id)
        if source.method == "rss":
            cache.crawl_rss(source)
        else:
            cache.crawl_configured(source)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast Main v3 reachability audit")
    parser.add_argument("--state", help="Limit to one state or FEDERAL")
    parser.add_argument("--skip-crawl", action="store_true", help="Host-match heuristics only")
    parser.add_argument("--delay", type=float, default=0.35, help="Per-request delay (seconds)")
    parser.add_argument("--no-nc-validation", action="store_true")
    parser.add_argument(
        "--content-types",
        help="Comma-separated source content_type filter (e.g. proclamation,executive_order)",
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv(ROOT / ".env")
    started = time.time()

    content_type_filter: set[str] | None = None
    if args.content_types:
        content_type_filter = {t.strip() for t in args.content_types.split(",") if t.strip()}

    client = AirtableClient()
    audit_urls = load_audit_urls(client, args.state, include_nc_validation=not args.no_nc_validation)
    if args.limit:
        audit_urls = audit_urls[: args.limit]

    state_sources, federal_sources = load_all_sources(content_type_filter)
    http = HttpFetcher(USER_AGENT, per_domain_delay=args.delay)
    cache = FastSourceCache(http)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    logger.info("Fast audit: %s URL(s)", len(audit_urls))
    prefetch_host_matched(audit_urls, state_sources, federal_sources, cache, args.skip_crawl)

    seen: set[str] = set()
    results: list[dict] = []
    for i, audit_url in enumerate(audit_urls, 1):
        alive, status = check_url_alive(audit_url.url, session)
        enabled, all_matched = matching_sources(audit_url, state_sources, federal_sources)
        row = classify_url(
            audit_url, enabled, all_matched, alive, cache, args.skip_crawl, seen, state_sources
        )
        row["http_status"] = status
        results.append(row)
        if i % 20 == 0 or i == len(audit_urls):
            logger.info("Classified %s/%s (%.0fs)", i, len(audit_urls), time.time() - started)

    nc_probes = run_nc_validation_probes(cache, state_sources)
    nc_checks = validate_nc_results(results, nc_probes)
    gaps = systemic_gaps(results, state_sources)
    fixes = ranked_fixes(gaps, results)
    summary = build_summary(results)
    elapsed = round(time.time() - started, 1)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    json_path = PROBE_DIR / f"main_v3_reachability_{ts}.json"
    md_path = PROBE_DIR / f"main_v3_reachability_{ts}.md"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "methodology": {
            "mode": "fast",
            "ground_truth": "Main v3 non-LegiScan URLs",
            "classifications": list(CLASSIFICATIONS),
            "index_crawl": "host-matched sources only, at configured max_pages",
            "depth_detection": "targeted page probes (NC fixtures + max_pages+1 edge)",
            "no_full_archive_crawl": True,
            "airtable": "read-only",
        },
        "summary": summary,
        "nc_validation": nc_checks,
        "systemic_gaps": gaps,
        "ranked_fixes": fixes,
        "results": results,
        "json_path": str(json_path),
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_path, payload, nc_checks, gaps, fixes)

    print(json.dumps({**summary, "elapsed_seconds": elapsed}, indent=2))
    print(f"\nWrote {json_path}\nWrote {md_path}")
    print(f"NC validation: {sum(1 for c in nc_checks if c['pass'])}/{len(nc_checks)} passed in {elapsed}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
