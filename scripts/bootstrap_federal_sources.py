#!/usr/bin/env python3
"""Bootstrap federal discovery sources from Main v3 + canonical USAO district template.

Ensures all 93 U.S. Attorney office sites (covering 94 federal districts) are present
even when Main v3 only seeds a handful of district URLs.
"""

from __future__ import annotations

import argparse
import json
import re
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

USAO_DISTRICTS_PATH = ROOT / "sources" / "usao_districts.json"
OUTPUT_PATH = ROOT / "sources" / "federal_sources.json"
REPORT_PATH = ROOT / "sources" / "federal_bootstrap_report.md"

FEDERAL_STATES = {"national", "us", "u.s.", "federal", ""}
FEDERAL_DOMAINS = {
    "justice.gov",
    "www.justice.gov",
    "federalregister.gov",
    "www.federalregister.gov",
    "whitehouse.gov",
    "www.whitehouse.gov",
    "bidenwhitehouse.archives.gov",
    "www.bidenwhitehouse.archives.gov",
}
URL_FIELDS = ["Bill Overview", "Bill Overview (Link)", "Bill Text", "Optional Link"]
USER_AGENT = "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)"

USAO_SLUG_RE = re.compile(r"justice\.gov/(usao-[a-z0-9-]+)", re.I)


def load_canonical_districts(refresh: bool = False) -> list[dict]:
    """Load canonical USAO districts; optionally refresh from justice.gov."""
    if refresh or not USAO_DISTRICTS_PATH.exists():
        refresh_usao_districts()
    data = json.loads(USAO_DISTRICTS_PATH.read_text(encoding="utf-8"))
    return data["districts"]


def refresh_usao_districts() -> None:
    """Scrape justice.gov find-your page and write sources/usao_districts.json."""
    response = requests.get(
        "https://www.justice.gov/usao/find-your-united-states-attorney",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    links = re.findall(r'href="(/usao-[a-z0-9-]+)"[^>]*>([^<]+)', response.text)
    districts: list[dict] = []
    seen: set[str] = set()
    for path, name in links:
        slug = path.lstrip("/")
        if slug == "usao-social-media-directory" or slug in seen:
            continue
        seen.add(slug)
        clean_name = re.sub(r"\s+", " ", name.replace("&amp;", "&").strip())
        clean_name = clean_name.replace(" &, ", " & ")
        districts.append(
            {
                "slug": slug,
                "name": clean_name,
                "office_url": f"https://www.justice.gov/{slug}",
                "press_url": f"https://www.justice.gov/{slug}/pr",
                "news_url": f"https://www.justice.gov/{slug}/news",
            }
        )
    districts.sort(key=lambda d: d["slug"])
    payload = {
        "source": "https://www.justice.gov/usao/find-your-united-states-attorney",
        "district_count": 94,
        "office_count": len(districts),
        "note": (
            "94 federal judicial districts; Guam and Northern Mariana Islands share "
            "usao-gu (93 office sites)."
        ),
        "districts": districts,
    }
    USAO_DISTRICTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USAO_DISTRICTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def load_main_v3_federal_urls() -> tuple[dict[str, dict], list[dict]]:
    """Harvest federal and USAO URLs from Main v3 Airtable."""
    from airtable_client import AirtableClient

    client = AirtableClient()
    usao_seeds: dict[str, dict] = defaultdict(
        lambda: {"sample_urls": [], "occurrence_count": 0, "states": set()}
    )
    other_federal: dict[tuple[str, str], dict] = {}

    for record in client.all_live_records():
        fields = record.get("fields") or {}
        state = str(fields.get("State") or "").strip()
        is_federal_record = state.lower() in FEDERAL_STATES

        for field in URL_FIELDS:
            url = fields.get(field)
            if not url or not isinstance(url, str) or not url.startswith("http"):
                continue

            host = urlparse(url).netloc.lower().removeprefix("www.")
            slug_match = USAO_SLUG_RE.search(url)

            if slug_match:
                slug = slug_match.group(1).lower()
                entry = usao_seeds[slug]
                entry["occurrence_count"] += 1
                entry["states"].add(state or "unknown")
                if url not in entry["sample_urls"]:
                    entry["sample_urls"].append(url)
                continue

            if not is_federal_record:
                continue
            if host not in {d.removeprefix("www.") for d in FEDERAL_DOMAINS}:
                continue

            key = (host, url)
            if key not in other_federal:
                other_federal[key] = {
                    "url": url,
                    "domain": host,
                    "sample_urls": [url],
                    "occurrence_count": 1,
                }
            else:
                other_federal[key]["occurrence_count"] += 1

    normalized_usao = {
        slug: {
            "sample_urls": info["sample_urls"],
            "occurrence_count": info["occurrence_count"],
            "states": sorted(info["states"]),
        }
        for slug, info in usao_seeds.items()
    }
    return normalized_usao, list(other_federal.values())


def probe_listing_url(slug: str) -> tuple[str, int, str]:
    """Pick best press/news listing URL for a district office.

    Prefer /pr and /news over the office homepage. Homepages are larger HTML
    but are not press indexes — a previous longest-body heuristic wrongly
    selected them for 91/93 districts.
    """
    candidates = [
        f"https://www.justice.gov/{slug}/pr",
        f"https://www.justice.gov/{slug}/news",
        f"https://www.justice.gov/{slug}/news-and-press-releases",
    ]
    headers = {"User-Agent": USER_AGENT}
    default = candidates[0]

    for url in candidates:
        try:
            response = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
            if response.status_code < 400:
                # Strip bot-management query params from the final URL.
                final = str(response.url).split("?", 1)[0].rstrip("/")
                return final, response.status_code, "probed"
        except Exception:
            continue

    return default, 0, "probe_failed_default_pr"


def curated_federal_seeds() -> list[dict]:
    """Non-USAO federal crawl targets."""
    return [
        {
            "state": "National",
            "name": "Federal Register — Executive Orders (API search)",
            "content_type": "executive_order",
            "method": "api",
            "api_url_template": (
                "https://www.federalregister.gov/api/v1/documents.json"
                "?conditions[type]=PRESDOCU&conditions[term]={query}&per_page=20"
            ),
            "search_queries": ["missing indigenous", "MMIP", "murdered indigenous women", "murdered indigenous"],
            "review_needed": False,
            "discovered_by": "curated",
            "source_id": "fed-fr-eo-search",
            "confidence": "high",
        },
        {
            "state": "National",
            "name": "DOJ — Press releases (News API)",
            "content_type": "press_release",
            "method": "api",
            "api_url_template": (
                "https://www.justice.gov/api/v1/press_releases.json"
                "?parameters[title]={query}&pagesize=20&sort=date&direction=DESC"
            ),
            "search_queries": ["indigenous", "MMIP", "Missing and Murdered", "tribal"],
            "review_needed": False,
            "discovered_by": "curated",
            "source_id": "fed-doj-news",
            "confidence": "high",
            "render_js": False,
            "ignore_robots": True,
            "notes": (
                "Official DOJ News API (bypasses Akamai HTML walls). "
                "Title filter only. /news HTML and USAO /pr listings remain bot-gated."
            ),
        },
        {
            "state": "National",
            "name": "White House — Briefing room",
            "content_type": "press_release",
            "method": "index",
            "url": "https://www.whitehouse.gov/briefing-room/",
            "review_needed": True,
            "discovered_by": "curated",
            "source_id": "fed-whitehouse-briefing",
            "confidence": "medium",
            "notes": "EO and policy announcements; verify current administration URL during review",
        },
    ]


def infer_usao_listing_from_seed(sample_urls: list[str], slug: str) -> str | None:
    """Derive a district press/news listing URL from a Main v3 deep link.

    Only accepts seeds under /pr or /news. File downloads and other paths
    must not collapse to the office homepage.
    """
    for url in sample_urls:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            continue
        if parts[0].lower() != slug.lower():
            continue
        if len(parts) >= 2 and parts[1].lower() in {"pr", "news"}:
            return f"{parsed.scheme}://{parsed.netloc}/{parts[0]}/{parts[1]}"
    return None


def build_usao_sources(
    districts: list[dict],
    main_v3_usao: dict[str, dict],
    probe: bool,
    delay: float,
) -> tuple[list[dict], dict]:
    """Merge canonical districts with Main v3 seeds."""
    sources: list[dict] = []
    stats = {
        "canonical_offices": len(districts),
        "main_v3_districts": len(main_v3_usao),
        "main_v3_slugs": sorted(main_v3_usao.keys()),
        "added_from_template": 0,
        "probe_ok": 0,
        "probe_failed": 0,
    }

    for district in districts:
        slug = district["slug"]
        seed = main_v3_usao.get(slug)
        discovered_by = "bootstrap_usao_template"
        sample_urls: list[str] = []
        occurrence_count = 0
        notes = district["name"]

        if seed:
            discovered_by = "bootstrap_main_v3_federal"
            sample_urls = list(seed["sample_urls"])
            occurrence_count = seed["occurrence_count"]
            notes = (
                f"{district['name']}; Main v3 seed from state(s) {', '.join(seed['states'])}"
            )
            url = infer_usao_listing_from_seed(sample_urls, slug) or district["press_url"]
        else:
            stats["added_from_template"] += 1
            url = district["press_url"]

        # Known district MMIP hub pages (when present) stay as sample seeds.
        mmip_hub = f"https://www.justice.gov/{slug}/missing-or-murdered-indigenous-persons"
        if mmip_hub not in sample_urls and slug == "usao-ak":
            sample_urls.append(mmip_hub)

        probe_status = None
        if probe:
            probed_url, probe_status, probe_note = probe_listing_url(slug)
            if probe_status and probe_status < 400:
                url = probed_url
                stats["probe_ok"] += 1
            else:
                stats["probe_failed"] += 1
                notes += f"; {probe_note}"
                url = district["press_url"]
            time.sleep(delay)

        # Never crawl the bare office homepage as the listing target.
        office = district["office_url"].rstrip("/")
        if url.rstrip("/") == office:
            url = district["press_url"]

        sources.append(
            {
                "state": "National",
                "name": f"USAO — {district['name']}",
                "content_type": "press_release",
                "method": "index",
                "url": url,
                "review_needed": not bool(seed),
                "discovered_by": discovered_by,
                "discovered_on": date.today().isoformat(),
                "source_id": slug,
                "confidence": "high" if seed else "medium",
                "notes": notes,
                "sample_urls": sample_urls,
                "occurrence_count": occurrence_count,
                "office_url": district["office_url"],
                "press_url_template": district["press_url"],
                "probe_status": probe_status,
                "render_js": True,
                "browser_wait_selector": "",
                "ignore_robots": True,
                # Page 1 is the bare /pr URL; ?page=N triggers Akamai bot walls.
                "max_pages": 1,
            }
        )

    return sources, stats


def build_other_federal_sources(other_federal: list[dict]) -> list[dict]:
    sources: list[dict] = []
    for entry in sorted(other_federal, key=lambda x: (-x["occurrence_count"], x["url"])):
        sources.append(
            {
                "state": "National",
                "name": f"Federal — {entry['domain']}",
                "content_type": "other",
                "method": "index",
                "url": entry["url"],
                "review_needed": True,
                "discovered_by": "bootstrap_main_v3_federal",
                "discovered_on": date.today().isoformat(),
                "source_id": f"fed-{entry['domain'].replace('.', '-')}",
                "confidence": "low",
                "notes": "Main v3 federal record; replace with listing page during review",
                "sample_urls": entry["sample_urls"],
                "occurrence_count": entry["occurrence_count"],
            }
        )
    return sources


def write_report(
    stats: dict,
    main_v3_usao: dict[str, dict],
    districts: list[dict],
    probe: bool,
) -> None:
    missing = sorted(set(d["slug"] for d in districts) - set(main_v3_usao.keys()))
    lines = [
        "# Federal Source Bootstrap Report",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "## USAO district coverage",
        "",
        f"- Canonical federal districts: **94** (93 office sites; Guam + NMI share `usao-gu`)",
        f"- Canonical office slugs loaded: **{stats['canonical_offices']}**",
        f"- Main v3 USAO districts found: **{stats['main_v3_districts']}**",
        f"- Added from canonical template (not in Main v3): **{stats['added_from_template']}**",
        "",
        "### Main v3 USAO seeds",
        "",
    ]
    if main_v3_usao:
        for slug in sorted(main_v3_usao):
            seed = main_v3_usao[slug]
            lines.append(
                f"- `{slug}` — {seed['occurrence_count']} ref(s), "
                f"states={seed['states']}, example={seed['sample_urls'][0]}"
            )
    else:
        lines.append("- None in Main v3 National/Federal records; state-level MMIP posts supplied AK/OR/MI seeds.")

    lines.extend(["", "### Districts added from canonical template", ""])
    for slug in missing:
        name = next(d["name"] for d in districts if d["slug"] == slug)
        lines.append(f"- `{slug}` — {name}")

    if probe:
        lines.extend(
            [
                "",
                "## Probe results",
                "",
                f"- Listing URLs confirmed: **{stats['probe_ok']}**",
                f"- Listing URLs not confirmed: **{stats['probe_failed']}**",
                "",
                "Probe tries `/pr`, then `/news`, then `/news-and-press-releases` "
                "(never the office homepage).",
            ]
        )

    lines.extend(
        [
            "",
            "## Next steps",
            "",
            "1. Review `sources/federal_sources.json` USAO rows",
            "2. Set `review_needed: false` on verified listing URLs",
            "3. Wire `FederalSiteSource` in discovery pipeline",
            "4. Run federal discovery dry-run against known Main v3 DOJ MMIP examples",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Bootstrap federal discovery sources")
    parser.add_argument(
        "--refresh-districts",
        action="store_true",
        help="Re-scrape justice.gov find-your page into sources/usao_districts.json",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="HTTP-probe each district listing URL (slow)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Delay between probe requests (seconds)",
    )
    parser.add_argument(
        "--no-airtable",
        action="store_true",
        help="Skip Main v3 harvest (template-only bootstrap)",
    )
    args = parser.parse_args()

    districts = load_canonical_districts(refresh=args.refresh_districts)
    main_v3_usao: dict[str, dict] = {}
    other_federal: list[dict] = []

    if not args.no_airtable:
        try:
            main_v3_usao, other_federal = load_main_v3_federal_urls()
        except Exception as exc:
            print(f"Warning: Main v3 harvest failed ({exc}); continuing with template only")

    usao_sources, stats = build_usao_sources(
        districts=districts,
        main_v3_usao=main_v3_usao,
        probe=args.probe,
        delay=args.delay,
    )
    sources = curated_federal_seeds() + build_other_federal_sources(other_federal) + usao_sources

    payload = {
        "generated_from": "Main v3 Airtable (National/Federal + USAO URLs) + canonical 94-district USAO template",
        "note": (
            "All 93 U.S. Attorney office sites are included. state=National for every row. "
            "Review listing URLs before setting review_needed=false."
        ),
        "usao_coverage": {
            "federal_districts": 94,
            "office_sites": len(districts),
            "main_v3_districts": stats["main_v3_districts"],
            "added_from_template": stats["added_from_template"],
        },
        "sources": sources,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    write_report(stats, main_v3_usao, districts, probe=args.probe)

    print(f"Wrote {len(sources)} federal source rows to {OUTPUT_PATH}")
    print(
        f"USAO coverage: {len(districts)} offices | "
        f"Main v3 seeds: {stats['main_v3_districts']} | "
        f"Added from template: {stats['added_from_template']}"
    )
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
