#!/usr/bin/env python3
"""Smoke-test and summarize state crawl source configs."""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.fetchers import HttpFetcher
from discovery.source_schema import StateSource, load_sources_data  # noqa: E402
from discovery.site_crawler import DEFAULT_SOURCES_PATH  # noqa: E402

USER_AGENT = "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)"
_http = HttpFetcher(USER_AGENT, per_domain_delay=0)


def load_sources(path: Path) -> list[StateSource]:
    with open(path, encoding="utf-8") as f:
        return load_sources_data(json.load(f))


def check_source(source: StateSource) -> tuple[bool, str]:
    if source.method == "api":
        api_key = os.getenv(source.api_key_env, "").strip()
        if not api_key:
            return False, f"missing env {source.api_key_env} (free key: legislation.nysenate.gov)"
        template = source.api_url_template or source.search_url
        query = (source.search_queries or ["MMIP"])[0]
        url = (
            template.replace("{query}", query)
            .replace("{api_key}", api_key)
        )
    else:
        url = source.primary_url()
        if source.method == "search" and source.search_queries:
            url = source.build_search_url(source.search_queries[0])
    if not url:
        return False, "missing url"
    ua = source.user_agent or USER_AGENT
    skip_robots = source.ignore_robots or os.getenv(
        "CRAWLER_IGNORE_ROBOTS", "false"
    ).lower() in ("1", "true", "yes")
    if not skip_robots and not _http.can_fetch(url, ua):
        return False, "robots.txt disallows fetch"
    try:
        response = requests.get(
            url,
            headers={"User-Agent": ua},
            timeout=20,
            allow_redirects=True,
            verify=source.ssl_verify,
        )
        if response.status_code >= 400:
            return False, f"HTTP {response.status_code}"
        if source.method == "api":
            payload = response.json()
            if not payload.get("success"):
                return False, payload.get("message", "api error")[:120]
            total = payload.get("total", 0)
            return True, f"ok ({total} hit(s))"
        if len(response.text) < 100:
            return False, "empty body"
        return True, "ok"
    except Exception as exc:
        return False, str(exc)[:120]


def main():
    parser = argparse.ArgumentParser(description="Validate state source configs")
    parser.add_argument(
        "--sources",
        default=str(DEFAULT_SOURCES_PATH),
        help="Path to state_sources.json",
    )
    parser.add_argument(
        "--review-queue",
        action="store_true",
        help="Only list sources with review_needed=true",
    )
    parser.add_argument(
        "--enabled-only",
        action="store_true",
        help="Only test sources with review_needed=false",
    )
    args = parser.parse_args()

    sources = load_sources(Path(args.sources))
    if args.review_queue:
        sources = [s for s in sources if s.review_needed]
    if args.enabled_only:
        sources = [s for s in sources if not s.review_needed]

    print(f"Checking {len(sources)} source(s)\n")
    ok_count = 0
    for source in sources:
        status = "REVIEW" if source.review_needed else "ENABLED"
        if source.review_needed and not args.review_queue:
            print(
                f"[{status}] {source.state} | {source.method:6} | {source.content_type:16} | {source.name}"
            )
            print(f"         {source.primary_url()}")
            if source.notes:
                print(f"         notes: {source.notes[:100]}")
            continue

        ok, detail = check_source(source)
        ok_count += int(ok)
        mark = "OK" if ok else "FAIL"
        print(
            f"[{mark}] [{status}] {source.state} | {source.method:6} | {source.content_type:16} | {source.name}"
        )
        print(f"       {source.primary_url()} -> {detail}")
        if source.notes:
            print(f"       notes: {source.notes[:100]}")

    if args.enabled_only or args.review_queue:
        print(f"\n{ok_count}/{len(sources)} passed smoke test")


if __name__ == "__main__":
    main()
