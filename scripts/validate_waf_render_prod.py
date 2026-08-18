#!/usr/bin/env python3
"""Prod render_js validation for WAF EO/proc (run in Docker)."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from discovery.browser_fetcher import BrowserRenderer
from discovery.fetchers import HttpFetcher
from discovery.source_schema import StateSource
from scripts.audit_eo_proc_endpoints import audit_one_source

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
http = HttpFetcher(UA, per_domain_delay=0.5)
browser = BrowserRenderer(UA)
browser.start()
TESTS = [
    ("KS", "executive_order", "https://www.governor.ks.gov/newsroom/executive-orders", ""),
    ("MA", "executive_order", "https://www.mass.gov/lists/governor-healeys-executive-orders", ""),
    ("MA", "proclamation", "https://www.mass.gov/lists/governor-healeys-proclamations", ""),
    ("NH", "executive_order", "https://www.governor.nh.gov/news-and-media/executive-orders", ""),
    ("NH", "proclamation", "https://www.governor.nh.gov/news-and-media/proclamations", ""),
    ("NY", "executive_order", "https://www.governor.ny.gov/executiveorders", ""),
    ("NY", "proclamation", "https://www.governor.ny.gov/proclamations", ""),
    ("PA", "executive_order", "https://www.pa.gov/en/agencies/oa/policies/view-policies#sortCriteria=%40copapwptitle%20ascending&f-copapwpcategory=Executive%20Order", "a[href*='/policies/eo/']"),
]
for state, ctype, url, wait in TESTS:
    src = StateSource(state=state, name=f"{state} {ctype}", content_type=ctype, method="index", url=url, ignore_robots=True, user_agent=UA, render_js=True, browser_wait_selector=wait)
    row = audit_one_source(src, http, browser, 3)
    print(f"{state} {ctype:16} {row['status']:22} eo={row['eo_proc_links']:3} bytes={row.get('index_bytes', 0)}")
    for ex in (row.get("examples") or [])[:2]:
        print(f"  {ex['title'][:50]} -> {ex['url'][:70]}")
browser.stop()
