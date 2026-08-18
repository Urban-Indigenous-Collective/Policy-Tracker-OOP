#!/usr/bin/env python3
"""Validate WAF-blocked EO/proc URLs (run on production host)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.fetchers import HttpFetcher
from discovery.source_schema import StateSource
from scripts.audit_eo_proc_endpoints import audit_one_source

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
http = HttpFetcher(UA, per_domain_delay=0.5)

TESTS = [
    ("KS", "executive_order", "KS EO", "https://www.governor.ks.gov/newsroom/executive-orders"),
    ("MA", "executive_order", "MA EO", "https://www.mass.gov/lists/governor-healeys-executive-orders"),
    ("MA", "proclamation", "MA proc", "https://www.mass.gov/info-details/current-massachusetts-proclamations"),
    ("NH", "executive_order", "NH EO", "https://www.governor.nh.gov/news-and-media/executive-orders"),
    ("NH", "proclamation", "NH proc", "https://www.governor.nh.gov/news-and-media/proclamations"),
    ("NY", "executive_order", "NY EO", "https://www.governor.ny.gov/executiveorders"),
    ("NY", "proclamation", "NY proc", "https://www.governor.ny.gov/proclamations"),
]

if __name__ == "__main__":
    for state, ctype, name, url in TESTS:
        src = StateSource(
            state=state,
            name=name,
            content_type=ctype,
            method="index",
            url=url,
            ignore_robots=True,
            user_agent=UA,
        )
        row = audit_one_source(src, http, None, 3)
        print(f"{state} {ctype:16} {row['status']:22} eo={row['eo_proc_links']:3} total={row['total_links']}")
