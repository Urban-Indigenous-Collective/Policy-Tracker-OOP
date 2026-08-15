#!/usr/bin/env python3
"""Bootstrap per-state MMIP crawl source manifests (51 states + DC).

Writes sources/manifests/{ST}.json for merge via scripts/merge_state_manifests.py.
Uses gov URL heuristics, optional live HEAD probes, and Main v3 seed domains.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.source_schema import (  # noqa: E402
    StateManifest,
    StateSource,
    is_blocked_domain,
)

MANIFESTS_DIR = ROOT / "sources" / "manifests"
REPORT_PATH = ROOT / "sources" / "bootstrap_report.md"
USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)",
)

# 50 states + DC
STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}

# Known high-value paths to probe on {state}.gov / governor domains
PROBE_TEMPLATES: list[tuple[str, str, str]] = [
    ("press_release", "index", "https://governor.{slug}.gov/news/press-releases"),
    ("press_release", "index", "https://gov.{slug}.gov/news/press-releases"),
    ("proclamation", "index", "https://governor.{slug}.gov/news/proclamations"),
    ("executive_order", "index", "https://governor.{slug}.gov/news/executive-orders"),
    ("executive_order", "index", "https://gov.{slug}.gov/news/executive-orders"),
    ("report", "index", "https://www.{slug}.gov/news/press-releases"),
    ("other", "search", "https://www.{slug}.gov/search?{param}={query}"),
]

SEARCH_PARAMS = ("q", "query", "search")

STATE_SLUGS: dict[str, str] = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "ca",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa",
    "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi", "MO": "mo",
    "MT": "montana", "NE": "nebraska", "NV": "nevada", "NH": "nh", "NJ": "nj",
    "NM": "newmexico", "NY": "ny", "NC": "nc", "ND": "nd", "OH": "ohio",
    "OK": "oklahoma", "OR": "oregon", "PA": "pa", "RI": "ri", "SC": "sc",
    "SD": "sd", "TN": "tennessee", "TX": "texas", "UT": "utah", "VT": "vermont",
    "VA": "virginia", "WA": "wa", "WV": "wv", "WI": "wisconsin", "WY": "wyo",
    "DC": "dc",
}

# Hand-curated seeds for states with non-obvious structures
MANUAL_SEEDS: dict[str, list[dict]] = {
    "NC": [
        {
            "name": "NC — NC Admin Indian Affairs media",
            "content_type": "report",
            "method": "index",
            "url": "https://ncadmin.nc.gov/news",
            "notes": "NC Department of Administration news",
            "confidence": "medium",
        },
        {
            "name": "NC — Governor news",
            "content_type": "press_release",
            "method": "index",
            "url": "https://governor.nc.gov/news",
            "confidence": "high",
        },
        {
            "name": "NC — nc.gov search",
            "content_type": "other",
            "method": "search",
            "search_url": "https://www.nc.gov/search?query={query}",
            "search_param": "query",
            "notes": "Site-wide search fallback for fragmented sections",
            "confidence": "medium",
        },
    ],
    "WA": [
        {
            "name": "WA — Governor newsroom",
            "content_type": "press_release",
            "method": "index",
            "url": "https://governor.wa.gov/news",
            "confidence": "high",
        },
    ],
    "NM": [
        {
            "name": "NM — Governor press releases",
            "content_type": "press_release",
            "method": "index",
            "url": "https://www.governor.state.nm.us/press-releases",
            "confidence": "high",
        },
    ],
    "NY": [
        {
            "name": "NY — Assembly press releases",
            "content_type": "press_release",
            "method": "index",
            "url": "https://www.nyassembly.gov/Press/",
            "notes": "www.nysenate.gov blocks automated requests (403); use Assembly + Open Legislation API for Senate bills",
            "confidence": "high",
        },
        {
            "name": "NY — Assembly site search",
            "content_type": "legislation",
            "method": "search",
            "search_url": "https://www.nyassembly.gov/search/?q={query}",
            "search_param": "q",
            "notes": "Server-rendered search; returns member stories and legislation links",
            "confidence": "high",
        },
        {
            "name": "NY — Governor news",
            "content_type": "press_release",
            "method": "index",
            "url": "https://www.governor.ny.gov/news",
            "confidence": "high",
        },
        {
            "name": "NY — Open Legislation API (Senate + Assembly bills)",
            "content_type": "legislation",
            "method": "api",
            "url": "https://legislation.nysenate.gov/api/3/bills/search",
            "api_url_template": "https://legislation.nysenate.gov/api/3/bills/search?term={query}&key={api_key}&limit=50",
            "api_key_env": "NY_OPEN_LEGISLATION_KEY",
            "notes": "Free API key at https://legislation.nysenate.gov/ — bill pages at legislation.nysenate.gov/bills/{year}/{printNo}",
            "confidence": "high",
        },
    ],
}


def load_main_v3_domains() -> dict[str, set[str]]:
    """Optional seed domains from Airtable Main v3."""
    domains: dict[str, set[str]] = defaultdict(set)
    try:
        from airtable_client import AirtableClient

        client = AirtableClient()
        skip = {"legiscan.com", "www.legiscan.com", "congress.gov", "justice.gov", "federalregister.gov"}
        for record in client.all_live_records():
            fields = record.get("fields") or {}
            state = str(fields.get("State") or "").strip().upper()
            if len(state) != 2 or state not in STATES:
                continue
            for field in ("Bill Overview (Link)", "Bill Text", "Optional Link"):
                url = fields.get(field)
                if not url or not isinstance(url, str):
                    continue
                host = urlparse(url).netloc.lower().removeprefix("www.")
                if any(s in host for s in skip):
                    continue
                domains[state].add(host)
    except Exception as exc:
        print(f"Note: could not load Main v3 seeds ({exc})")
    return domains


def probe_url(url: str) -> bool:
    if is_blocked_domain(url):
        return False
    try:
        response = requests.head(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=12,
            allow_redirects=True,
        )
        if response.status_code == 405:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=12,
                allow_redirects=True,
            )
        return response.status_code < 400
    except Exception:
        return False


def build_probe_sources(state: str, slug: str, probe: bool) -> list[StateSource]:
    sources: list[StateSource] = []
    for content_type, method, template in PROBE_TEMPLATES:
        if method == "search":
            for param in SEARCH_PARAMS:
                url = template.format(slug=slug, param=param, query="{query}")
                if probe and not probe_url(url.replace("{query}", "MMIP")):
                    continue
                sources.append(
                    StateSource(
                        state=state,
                        name=f"{state} — {slug}.gov site search ({param})",
                        content_type="other",
                        method="search",
                        search_url=url,
                        search_param=param,
                        review_needed=True,
                        discovered_by="bootstrap_probe",
                        notes="Auto-probed site search endpoint",
                        confidence="low",
                    )
                )
                break
            continue

        url = template.format(slug=slug, param="q", query="MMIP")
        if probe and not probe_url(url):
            continue
        label = content_type.replace("_", " ")
        sources.append(
            StateSource(
                state=state,
                name=f"{state} — Governor {label}",
                content_type=content_type,  # type: ignore[arg-type]
                method="index",
                url=url,
                review_needed=True,
                discovered_by="bootstrap_probe",
                notes="Auto-probed governor/news path",
                confidence="medium",
            )
        )
    return sources


def is_gov_domain(domain: str) -> bool:
    """Only official government hosts belong in crawl manifests."""
    lowered = domain.lower()
    return lowered.endswith(".gov") or ".state." in lowered


def domain_index_sources(state: str, domains: set[str]) -> list[StateSource]:
    sources: list[StateSource] = []
    for domain in sorted(domains):
        if not is_gov_domain(domain):
            continue
        url = f"https://{domain}/"
        sources.append(
            StateSource(
                state=state,
                name=f"{state} — {domain} (Main v3 seed)",
                content_type="other",
                method="index",
                url=url,
                review_needed=True,
                discovered_by="bootstrap_main_v3",
                notes="Domain seen in Main v3; replace url with listing page during review",
                confidence="low",
            )
        )
    return sources


def bootstrap_state(
    state: str,
    main_v3_domains: set[str],
    probe: bool,
) -> StateManifest:
    slug = STATE_SLUGS.get(state, state.lower())
    sources: list[StateSource] = []

    for raw in MANUAL_SEEDS.get(state, []):
        sources.append(
            StateSource(
                state=state,
                review_needed=True,
                discovered_by="bootstrap_manual",
                discovered_on=date.today().isoformat(),
                **raw,
            )
        )

    sources.extend(build_probe_sources(state, slug, probe=probe))
    sources.extend(domain_index_sources(state, main_v3_domains))

    # Dedupe by primary url
    seen: set[str] = set()
    unique: list[StateSource] = []
    for source in sources:
        key = source.primary_url().lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)

    return StateManifest(state=state, sources=unique)


def write_manifest(manifest: StateManifest) -> None:
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = MANIFESTS_DIR / f"{manifest.state}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest.model_dump(), f, indent=2)
        f.write("\n")


def write_report(results: dict[str, StateManifest]) -> None:
    lines = [
        "# State Source Bootstrap Report",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "## Summary",
        "",
    ]
    total = sum(len(m.sources) for m in results.values())
    empty = [st for st, m in results.items() if not m.sources]
    lines.append(f"- States processed: {len(results)}")
    lines.append(f"- Total proposed sources: {total}")
    lines.append(f"- States with zero sources: {len(empty)}")
    lines.append("")
    lines.append("## Per-state counts")
    lines.append("")
    lines.append("| State | Sources |")
    lines.append("|-------|---------|")
    for st in sorted(results):
        lines.append(f"| {st} | {len(results[st].sources)} |")
    if empty:
        lines.extend(["", "## States needing manual research", ""])
        lines.extend(f"- {st}" for st in empty)

    low_confidence = [
        s
        for m in results.values()
        for s in m.sources
        if s.confidence == "low" or (s.method == "search" and s.discovered_by == "bootstrap_probe")
    ]
    if low_confidence:
        lines.extend(["", "## Low-confidence / search-only sources", ""])
        for s in sorted(low_confidence, key=lambda x: (x.state, x.name)):
            lines.append(f"- **{s.state}** {s.name} ({s.method}) — {s.primary_url()}")

    legislature_sources = [
        s
        for m in results.values()
        for s in m.sources
        if s.content_type == "legislation" or "leg." in s.primary_url().lower()
    ]
    if legislature_sources:
        lines.extend(
            [
                "",
                "## Legislature / legislation URLs (keep — complement LegiScan)",
                "",
                "Official legislature sites may host committee reports, session docs, and",
                "pages LegiScan does not index. Replace domain homepages with listing URLs.",
                "",
            ]
        )
        for s in sorted(legislature_sources, key=lambda x: (x.state, x.name)):
            lines.append(f"- **{s.state}** {s.name} — {s.primary_url()}")

    lines.extend(
        [
            "",
            "## Next steps",
            "",
            "1. Review each source URL in `sources/manifests/*.json`",
            "2. Replace seed/index URLs with real listing pages where needed",
            "3. Set `review_needed: false` on approved rows",
            "4. Run `python scripts/merge_state_manifests.py`",
            "5. Run `python scripts/validate_state_sources.py --enabled-only`",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    load_dotenv(ROOT / ".env")
    import argparse

    parser = argparse.ArgumentParser(description="Bootstrap state crawl manifests")
    parser.add_argument(
        "--states",
        nargs="*",
        help="Limit to state codes (default: all 51)",
    )
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="Skip live HTTP probes (faster, more speculative URLs)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between probe requests",
    )
    args = parser.parse_args()

    target_states = [s.upper() for s in args.states] if args.states else sorted(STATES.keys())
    main_v3 = load_main_v3_domains()
    results: dict[str, StateManifest] = {}

    for state in target_states:
        if state not in STATES:
            print(f"Skipping unknown state code: {state}")
            continue
        manifest = bootstrap_state(state, main_v3.get(state, set()), probe=not args.no_probe)
        write_manifest(manifest)
        results[state] = manifest
        print(f"{state}: {len(manifest.sources)} source(s)")
        if not args.no_probe:
            time.sleep(args.delay)

    write_report(results)
    print(f"\nManifests written to {MANIFESTS_DIR}")
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
