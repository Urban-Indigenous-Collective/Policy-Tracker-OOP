#!/usr/bin/env python3
"""Audit state MMIP source coverage: governor, legislature, and chamber gaps.

Checks sources/manifests/*.json (and optionally state_sources.json) for:
  - Governor: news/press, executive orders, proclamations, DOA/agency releases
  - Legislature: bill search, session listings, chamber-specific sources
  - Bicameral: House + Senate (Nebraska unicameral exception)

Usage:
  python scripts/audit_source_coverage.py
  python scripts/audit_source_coverage.py --json
  python scripts/audit_source_coverage.py --include-review
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent

MANIFESTS_DIR = ROOT / "sources" / "manifests"
STATE_SOURCES_PATH = ROOT / "sources" / "state_sources.json"


def _src_url(raw: dict) -> str:
    method = raw.get("method") or "index"
    if method == "rss":
        return (raw.get("rss_url") or raw.get("url") or "").lower()
    if method == "search":
        return (raw.get("search_url") or raw.get("url") or "").lower()
    if method == "api":
        return (raw.get("api_url_template") or raw.get("search_url") or raw.get("url") or "").lower()
    return (raw.get("url") or "").lower()

# 50 states + DC (matches bootstrap_state_sources_agents.py)
ALL_STATES = sorted(
    [
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    ]
)

UNICAMERAL = {"NE"}

GOVERNOR_HOST_RE = re.compile(
    r"(^|\.)((governor|gov)\.[a-z0-9.-]+|governor\.[a-z]{2}\.gov)",
    re.I,
)
LEGISLATURE_HOST_RE = re.compile(
    r"(legislature|legis|legstate|leg\.|assembly|senate|house|"
    r"nmlegis|capitol|openleg|nysenate\.gov/legislation)",
    re.I,
)
GENERIC_STATE_SEARCH_RE = re.compile(
    r"^https?://(www\.)?[a-z]{2}\.gov/search", re.I
)
MAIN_V3_SEED_RE = re.compile(r"\(Main v3 seed\)", re.I)
DOA_RE = re.compile(
    r"(doa\.|department.of.admin|ncadmin|dept\.of\.admin|"
    r"administration\.|indian.affairs|native.american)",
    re.I,
)
HOUSE_RE = re.compile(
    r"(house|assembly|representatives|delegates|nyassembly|"
    r"lower.chamber|houseofrep)",
    re.I,
)
SENATE_RE = re.compile(
    r"(senate|upper.chamber|nysenate|open.legislation)",
    re.I,
)
BOTH_CHAMBERS_RE = re.compile(
    r"(both.chamber|bicameral|senate.and.assembly|assembly.and.senate|"
    r"open.legislation.api)",
    re.I,
)
SESSION_RE = re.compile(
    r"(bill/search|bills/introduced|session|bill.status|legislation|"
    r"billsearch|open.legislation)",
    re.I,
)


@dataclass
class SourceTags:
    governor_news: bool = False
    governor_search: bool = False
    executive_order: bool = False
    proclamation: bool = False
    doa: bool = False
    generic_search: bool = False
    main_v3_seed: bool = False
    legislature_general: bool = False
    bill_search: bool = False
    session_listing: bool = False
    house: bool = False
    senate: bool = False
    both_chambers: bool = False
    low_confidence: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class StateCoverage:
    state: str
    source_count: int = 0
    enabled_count: int = 0
    governor: str = "MISSING"  # FULL | PARTIAL | MISSING
    legislature: str = "MISSING"
    chambers: str = "MISSING"  # FULL | PARTIAL | MISSING | N/A (NE)
    governor_detail: list[str] = field(default_factory=list)
    legislature_detail: list[str] = field(default_factory=list)
    chamber_detail: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    sources_matched: dict[str, list[str]] = field(default_factory=dict)


def _url(source: dict) -> str:
    return _src_url(source)


def _text_blob(source: dict) -> str:
    return " ".join(
        filter(
            None,
            [
                source.get("name", ""),
                source.get("notes", ""),
                _url(source),
                source.get("content_type", ""),
            ],
        )
    ).lower()


def tag_source(source: dict) -> SourceTags:
    url = _url(source)
    blob = _text_blob(source)
    host = urlparse(url).netloc.lower() if url else ""
    tags = SourceTags()

    if source.get("confidence") == "low":
        tags.low_confidence = True
    if MAIN_V3_SEED_RE.search(source.get("name", "")):
        tags.main_v3_seed = True

    # Governor signals
    is_gov_host = bool(GOVERNOR_HOST_RE.search(host)) or "governor" in blob
    method = source.get("method") or "index"
    content_type = source.get("content_type") or "other"
    if is_gov_host and method in ("index", "rss"):
        if content_type in ("press_release", "report", "letter", "other"):
            tags.governor_news = True
    if is_gov_host and method == "search":
        tags.governor_search = True
    if content_type == "executive_order" or "executive-order" in url or "executive order" in blob:
        tags.executive_order = True
    if content_type == "proclamation" or "proclamation" in url:
        tags.proclamation = True
    if DOA_RE.search(blob) or DOA_RE.search(host):
        tags.doa = True
    if method == "search" and GENERIC_STATE_SEARCH_RE.match(url):
        tags.generic_search = True
        if not is_gov_host:
            tags.generic_search = True

    # Legislature signals
    is_leg = bool(LEGISLATURE_HOST_RE.search(host)) or bool(LEGISLATURE_HOST_RE.search(blob))
    if is_leg or content_type == "legislation":
        tags.legislature_general = True
    if method in ("search", "api") and (is_leg or content_type == "legislation"):
        tags.bill_search = True
    if SESSION_RE.search(url) or SESSION_RE.search(blob):
        tags.session_listing = True
    if BOTH_CHAMBERS_RE.search(blob) or (method == "api" and "legislation" in url):
        tags.both_chambers = True
    if HOUSE_RE.search(blob) and not tags.both_chambers:
        tags.house = True
    if SENATE_RE.search(blob) and not tags.both_chambers:
        tags.senate = True

    # VT-style unified legislature pages count as both if they mention both chambers
    if "both chamber" in blob:
        tags.both_chambers = True

    return tags


def merge_tags(sources: list[dict]) -> tuple[SourceTags, dict[str, list[str]]]:
    merged = SourceTags()
    matched: dict[str, list[str]] = {}

    def _set(field: str, source: dict) -> None:
        matched.setdefault(field, []).append(source.get("name", "?"))

    for source in sources:
        tags = tag_source(source)
        for attr in SourceTags.__dataclass_fields__:
            if getattr(tags, attr):
                setattr(merged, attr, True)
                _set(attr, source)

    return merged, matched


def classify_governor(tags: SourceTags) -> tuple[str, list[str], list[str], list[str]]:
    detail: list[str] = []
    gaps: list[str] = []
    false_positives: list[str] = []

    has_real = tags.governor_news or tags.executive_order or tags.proclamation or tags.doa
    has_gov_any = has_real or tags.governor_search

    if tags.governor_news:
        detail.append("governor news/press index")
    if tags.executive_order:
        detail.append("executive orders")
    if tags.proclamation:
        detail.append("proclamations")
    if tags.doa:
        detail.append("DOA/agency press")
    if tags.governor_search:
        detail.append("governor site search")
    if tags.generic_search and not has_real:
        false_positives.append("generic state.gov search-only (may miss governor/DOA pages)")
    if tags.main_v3_seed and not has_real:
        false_positives.append("Main v3 domain homepage seed (not a listing page)")

    if not has_gov_any and not tags.generic_search and not tags.main_v3_seed:
        gaps.append("Add governor news index (e.g. governor.{st}.gov/news)")
        gaps.append("Add executive orders listing if published separately")
        gaps.append("Add proclamations listing or DOA press releases (some states publish MMIP proclamations via DOA)")
        return "MISSING", detail, gaps, false_positives

    if has_real:
        missing_bits = []
        if not tags.governor_news and not tags.governor_search:
            missing_bits.append("governor news/press listing")
        if not tags.executive_order:
            missing_bits.append("executive orders index")
        if not tags.proclamation and not tags.doa:
            missing_bits.append("proclamations or DOA/agency press releases")
        if missing_bits:
            for bit in missing_bits:
                gaps.append(f"Consider adding {bit}")
            return "PARTIAL", detail, gaps, false_positives
        return "FULL", detail, gaps, false_positives

    # Only weak signals
    if tags.generic_search:
        gaps.append("Replace generic state search with governor.{st}.gov/news index")
        gaps.append("Add DOA press releases if proclamations publish there (see NC doa.nc.gov)")
    if tags.main_v3_seed:
        gaps.append("Replace Main v3 homepage seeds with real governor listing URLs")
    return "PARTIAL", detail, gaps, false_positives


def classify_legislature(tags: SourceTags) -> tuple[str, list[str], list[str]]:
    detail: list[str] = []
    gaps: list[str] = []

    has_leg = tags.legislature_general or tags.bill_search or tags.session_listing
    if tags.bill_search:
        detail.append("bill search or legislation API")
    if tags.session_listing:
        detail.append("session/bill listing")
    if tags.legislature_general:
        detail.append("legislature domain source")

    if not has_leg:
        gaps.append("Add legislature bill search (keyword MMIP queries)")
        gaps.append("Add session bill listing page (e.g. /bills/introduced/{year})")
        return "MISSING", detail, gaps

    if tags.legislature_general and not tags.bill_search and not tags.session_listing:
        gaps.append("Replace legislature homepage with bill search or session listing URL")
        return "PARTIAL", detail, gaps

    if not tags.bill_search:
        gaps.append("Add legislature keyword/bill search endpoint")
    if not tags.session_listing and not tags.bill_search:
        gaps.append("Add bills-introduced or session documents listing")

    if tags.bill_search and (tags.session_listing or tags.legislature_general):
        return "FULL", detail, gaps
    return "PARTIAL", detail, gaps


def classify_chambers(state: str, tags: SourceTags) -> tuple[str, list[str], list[str]]:
    if state in UNICAMERAL:
        detail = []
        if tags.legislature_general or tags.bill_search or tags.session_listing:
            detail.append("unicameral legislature (single chamber OK)")
            return "N/A", detail, []
        return "N/A", [], ["Nebraska: add nebraskalegislature.gov bill search/listing"]

    detail: list[str] = []
    gaps: list[str] = []

    if tags.both_chambers:
        detail.append("unified source covers both chambers")
        return "FULL", detail, gaps

    has_house = tags.house
    has_senate = tags.senate

    if has_house:
        detail.append("house/assembly source")
    if has_senate:
        detail.append("senate source")

    if has_house and has_senate:
        return "FULL", detail, gaps
    if has_house or has_senate:
        missing = "senate" if has_house else "house/assembly"
        gaps.append(f"Add {missing}-specific bill search or press listing")
        return "PARTIAL", detail, gaps

    if tags.legislature_general or tags.bill_search or tags.session_listing:
        gaps.append("Add chamber-specific sources (house + senate) or unified API covering both")
        return "PARTIAL", detail, gaps

    gaps.append("Add house/assembly and senate bill search or press sources")
    return "MISSING", detail, gaps


def audit_state(state: str, sources: list[dict]) -> StateCoverage:
    tags, matched = merge_tags(sources)
    cov = StateCoverage(
        state=state,
        source_count=len(sources),
        enabled_count=sum(1 for s in sources if not s.get("review_needed", True)),
        sources_matched=matched,
    )

    gov_status, gov_detail, gov_gaps, fps = classify_governor(tags)
    leg_status, leg_detail, leg_gaps = classify_legislature(tags)
    chamber_status, chamber_detail, chamber_gaps = classify_chambers(state, tags)

    cov.governor = gov_status
    cov.legislature = leg_status
    cov.chambers = chamber_status
    cov.governor_detail = gov_detail
    cov.legislature_detail = leg_detail
    cov.chamber_detail = chamber_detail
    cov.gaps = gov_gaps + leg_gaps + chamber_gaps
    cov.false_positives = fps

    # Main v3 seeds on legislature domains are false positives too
    if tags.main_v3_seed and tags.legislature_general and leg_status != "FULL":
        cov.false_positives.append("Main v3 legislature homepage seed (replace with bill search URL)")

    return cov


def load_manifest(state: str) -> list[dict]:
    path = MANIFESTS_DIR / f"{state}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("sources", [])


def load_merged() -> list[dict]:
    if not STATE_SOURCES_PATH.exists():
        return []
    with open(STATE_SOURCES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("sources", data) if isinstance(data, dict) else data


def print_report(results: list[StateCoverage], label: str) -> None:
    full_gov = sum(1 for r in results if r.governor == "FULL")
    partial_gov = sum(1 for r in results if r.governor == "PARTIAL")
    missing_gov = sum(1 for r in results if r.governor == "MISSING")
    full_leg = sum(1 for r in results if r.legislature == "FULL")
    partial_leg = sum(1 for r in results if r.legislature == "PARTIAL")
    missing_leg = sum(1 for r in results if r.legislature == "MISSING")
    full_ch = sum(1 for r in results if r.chambers == "FULL")
    partial_ch = sum(1 for r in results if r.chambers == "PARTIAL")
    missing_ch = sum(1 for r in results if r.chambers == "MISSING")
    na_ch = sum(1 for r in results if r.chambers == "N/A")

    both_full = sum(
        1 for r in results
        if r.governor == "FULL" and r.legislature == "FULL"
        and (r.chambers == "FULL" or r.chambers == "N/A")
    )

    print(f"\n{'=' * 72}")
    print(f"MMIP SOURCE COVERAGE AUDIT — {label}")
    print(f"{'=' * 72}\n")

    print("## Summary counts\n")
    print(f"| Dimension | FULL | PARTIAL | MISSING | N/A |")
    print(f"|-----------|------|---------|---------|-----|")
    print(f"| Governor | {full_gov} | {partial_gov} | {missing_gov} | — |")
    print(f"| Legislature | {full_leg} | {partial_leg} | {missing_leg} | — |")
    print(f"| Chambers | {full_ch} | {partial_ch} | {missing_ch} | {na_ch} |")
    print(f"\nStates with FULL governor + FULL legislature + chambers OK: **{both_full}/51**\n")

    def _section(title: str, predicate) -> None:
        items = [r for r in results if predicate(r)]
        print(f"## {title} ({len(items)})\n")
        if not items:
            print("_None_\n")
            return
        for r in sorted(items, key=lambda x: x.state):
            detail = ", ".join(r.governor_detail) or "—"
            fps = f" ⚠ {r.false_positives[0]}" if r.false_positives else ""
            print(f"- **{r.state}** [{r.governor}] ({r.source_count} sources, {r.enabled_count} enabled) — {detail}{fps}")
            for gap in r.gaps[:4]:
                print(f"  - → {gap}")
        print()

    _section("Governor MISSING or PARTIAL", lambda r: r.governor in ("MISSING", "PARTIAL"))
    _section("Legislature MISSING or PARTIAL", lambda r: r.legislature in ("MISSING", "PARTIAL"))
    _section(
        "Chamber gaps (excluding NE unicameral)",
        lambda r: r.state not in UNICAMERAL and r.chambers in ("MISSING", "PARTIAL"),
    )

    print("## Top priority fixes\n")
    priority = []
    for r in results:
        score = 0
        if r.governor == "MISSING":
            score += 10
        elif r.governor == "PARTIAL" and r.false_positives:
            score += 7
        if r.legislature == "MISSING":
            score += 10
        elif r.legislature == "PARTIAL":
            score += 5
        if r.state not in UNICAMERAL and r.chambers in ("MISSING", "PARTIAL"):
            score += 4
        if r.source_count <= 1:
            score += 3
        if score >= 7:
            priority.append((score, r))

    for score, r in sorted(priority, key=lambda x: (-x[0], x[1].state))[:20]:
        print(f"- **{r.state}** (priority {score}): gov={r.governor}, leg={r.legislature}, chambers={r.chambers}")
        if r.gaps:
            print(f"  - {r.gaps[0]}")
    print()

    print("## False-positive patterns (search-only / homepage seeds)\n")
    fp_states = [r for r in results if r.false_positives]
    for r in sorted(fp_states, key=lambda x: x.state):
        for fp in r.false_positives:
            print(f"- **{r.state}**: {fp}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit MMIP source coverage gaps")
    parser.add_argument("--include-review", action="store_true", help="Include review_needed sources")
    parser.add_argument("--merged", action="store_true", help="Audit state_sources.json instead of manifests")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    if args.merged:
        all_sources = load_merged()
        by_state: dict[str, list[dict]] = {st: [] for st in ALL_STATES}
        for s in all_sources:
            st = (s.get("state") or "").upper()
            if st in by_state:
                by_state[st].append(s)
        label = "state_sources.json (merged)"
    else:
        by_state = {st: load_manifest(st) for st in ALL_STATES}
        label = "sources/manifests/*.json"

    if not args.include_review:
        by_state = {
            st: [s for s in srcs if not s.get("review_needed", True)]
            for st, srcs in by_state.items()
        }

    results = [audit_state(st, by_state[st]) for st in ALL_STATES]

    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
    else:
        print_report(results, label)

    missing_manifests = [st for st in ALL_STATES if not (MANIFESTS_DIR / f"{st}.json").exists()]
    if missing_manifests:
        print(f"## Missing manifest files: {', '.join(missing_manifests)}\n")


if __name__ == "__main__":
    main()
