#!/usr/bin/env python3
"""Extended prod probes for NY/KS/NH/PA."""
import re, sys
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

# NY long settle
html, _ = browser.fetch("https://www.governor.ny.gov/executiveorders", user_agent=UA, settle_ms=20000, timeout_ms=120000)
print("NY long settle len", len(html))
if html:
    t = re.search(r"<title>([^<]+)", html, re.I)
    print("  title:", t.group(1)[:80] if t else "?")
    links = re.findall(r'href="([^"]+)"', html)
    eo = [l for l in links if "executive-order" in l or "/executiveorders" in l or ".pdf" in l.lower()]
    print("  eo-ish links:", len(eo), eo[:5])

TESTS = [
    ("KS", "executive_order", "https://governor.kansas.gov/newsroom/executive-orders"),
    ("NH", "executive_order", "https://governor.nh.gov/news-and-media/executive-orders"),
    ("PA", "executive_order", "https://www.pa.gov/governor/newsroom/2026-press-releases"),
]
for state, ctype, url in TESTS:
    src = StateSource(state=state, name="probe", content_type=ctype, method="index", url=url, ignore_robots=True, user_agent=UA, render_js=True, max_pages=2)
    row = audit_one_source(src, http, browser, 3)
    print(f"{state} {row['status']:22} eo={row['eo_proc_links']:3} {url[:60]}")
    for ex in (row.get("examples") or [])[:2]:
        print(f"  {ex['title'][:50]} -> {ex['url'][:70]}")

browser.stop()
