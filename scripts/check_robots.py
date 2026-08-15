#!/usr/bin/env python3
"""Report (and optionally fix) sources blocked by robots.txt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.fetchers import HttpFetcher
from discovery.source_schema import StateManifest, StateSource, load_sources_data
from discovery.site_crawler import DEFAULT_SOURCES_PATH
from validate_state_sources import check_source

USER_AGENT = "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)"


def test_url(source: StateSource) -> str:
    if source.method == "api":
        return source.primary_url()
    if source.method == "search" and source.search_queries:
        return source.build_search_url(source.search_queries[0])
    return source.primary_url()


def main() -> None:
    parser = argparse.ArgumentParser(description="Find robots.txt-blocked crawl sources")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES_PATH))
    parser.add_argument("--fix", action="store_true", help="Set ignore_robots=true on blocked sources in manifests")
    parser.add_argument("--enabled-only", action="store_true", default=True)
    args = parser.parse_args()

    sources = load_sources_data(json.loads(Path(args.sources).read_text(encoding="utf-8")))
    if args.enabled_only:
        sources = [s for s in sources if not s.review_needed]

    http = HttpFetcher(USER_AGENT, per_domain_delay=0)
    blocked: list[tuple[StateSource, str]] = []

    print(f"Checking robots.txt for {len(sources)} enabled source(s)\n")
    for source in sources:
        url = test_url(source)
        if not url:
            continue
        robots_ok = http.can_fetch(url)
        ok, detail = check_source(source)
        if not robots_ok:
            blocked.append((source, url))
            http_note = detail if ok else f"http: {detail}"
            print(f"[ROBOTS] {source.state} | {source.name}")
            print(f"         {url}")
            if not ok and "robots" not in detail:
                print(f"         ({http_note})")
        elif not ok:
            print(f"[HTTP FAIL] {source.state} | {source.name} -> {detail}")

    print(f"\n{len(blocked)} source(s) reachable but blocked by robots.txt")
    if not args.fix or not blocked:
        return

    by_state: dict[str, list[StateSource]] = {}
    blocked_ids = {s.source_id for s, _ in blocked}
    for source in sources:
        by_state.setdefault(source.state, []).append(source)

    for state, state_sources in sorted(by_state.items()):
        manifest_path = ROOT / "sources" / "manifests" / f"{state}.json"
        if not manifest_path.exists():
            continue
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        changed = False
        for raw in data.get("sources", []):
            sid = raw.get("source_id") or ""
            if sid in blocked_ids:
                if not raw.get("ignore_robots"):
                    raw["ignore_robots"] = True
                    changed = True
        if changed:
            manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"Updated {manifest_path.name}")

    print("\nRun: python scripts/merge_state_manifests.py")


if __name__ == "__main__":
    main()
