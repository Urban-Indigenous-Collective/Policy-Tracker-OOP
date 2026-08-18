#!/usr/bin/env python3
"""Validate EO/proc candidates for the 7 remaining gap jurisdictions.

Run on production Docker for WAF/render_js sources:
  docker compose run --rm --no-deps scheduler python scripts/validate_remaining_eo_proc.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.browser_fetcher import BrowserRenderer  # noqa: E402
from discovery.fetchers import HttpFetcher  # noqa: E402
from discovery.source_schema import StateSource  # noqa: E402
from scripts.audit_eo_proc_endpoints import audit_one_source  # noqa: E402

USER_AGENT = "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# (state, content_type, name, url, kwargs)
CANDIDATES = [
    # --- WAF states: render_js + browser UA ---
    ("KS", "executive_order", "KS EO render_js", "https://www.governor.ks.gov/newsroom/executive-orders", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("MA", "executive_order", "MA EO render_js", "https://www.mass.gov/lists/governor-healeys-executive-orders", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("MA", "proclamation", "MA proc render_js", "https://www.mass.gov/info-details/current-massachusetts-proclamations", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("NH", "executive_order", "NH EO render_js", "https://www.governor.nh.gov/news-and-media/executive-orders", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("NH", "proclamation", "NH proc render_js", "https://www.governor.nh.gov/news-and-media/proclamations", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("NY", "executive_order", "NY EO render_js", "https://www.governor.ny.gov/executiveorders", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("NY", "proclamation", "NY proc render_js", "https://www.governor.ny.gov/proclamations", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    # --- PA: Coveo variants ---
    ("PA", "executive_order", "PA EO Coveo hash", "https://www.pa.gov/agencies/oa/policies/view-policies#sortCriteria=%40copapwptitle%20ascending&f-copapwpcategory=Executive%20Order", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
        "browser_wait_selector": "a[href*='/policies/eo/']",
    }),
    ("PA", "executive_order", "PA EO Coveo result", "https://www.pa.gov/agencies/oa/policies/view-policies", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
        "browser_wait_selector": ".CoveoResultLink, a[href*='eo']",
    }),
    ("PA", "executive_order", "PA EO policies index", "https://www.pa.gov/agencies/oa/policies", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
        "browser_wait_selector": "a[href*='Executive']",
    }),
    ("PA", "executive_order", "PA SOS EO search", "https://www.dos.pa.gov/Records/ExecutiveOrders/Pages/default.aspx", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("PA", "executive_order", "PA governor EO", "https://governor.pa.gov/executive-orders/", {
        "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("PA", "executive_order", "PA governor EO alt", "https://www.pa.gov/governor/executive-orders", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    # --- KY: thorough re-search ---
    ("KY", "executive_order", "KY orders SharePoint", "https://governor.ky.gov/orders/Pages/default.aspx", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("KY", "executive_order", "KY newsroom EO", "https://governor.ky.gov/newsroom/Pages/Executive-Orders.aspx", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("KY", "executive_order", "KY SOS journal", "https://web.sos.ky.gov/executivejournal/", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("KY", "executive_order", "KY SOS exec orders", "https://apps.legislature.ky.gov/law/executiveorders/", {
        "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("KY", "executive_order", "KY disaster EO", "https://governor.ky.gov/Newsroom/Pages/Disaster-Declarations.aspx", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    # --- WY: render_js on SPA paths + alternates ---
    ("WY", "executive_order", "WY EO render_js", "https://governor.wyo.gov/news/executive-orders", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("WY", "proclamation", "WY proc render_js", "https://governor.wyo.gov/news/proclamations", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("WY", "executive_order", "WY SOS exec orders", "https://sos.wyo.gov/Administration/ExecutiveOrders.aspx", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("WY", "executive_order", "WY state EO archive", "https://wyo.gov/governor/executive-orders", {
        "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("WY", "executive_order", "WY library EO", "https://library.wyo.gov/government/executive-orders/", {
        "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("WY", "executive_order", "WY EO state-government", "https://governor.wyo.gov/state-government/executive-orders", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    # --- Round 2: alternate archives ---
    ("PA", "executive_order", "PA pacode index", "https://www.pacodeandbulletin.gov/secure/pacode/data/004/chapter1/s1.4.html", {
        "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("PA", "executive_order", "PA index-of-issuances", "https://www.pa.gov/agencies/oa/policies/index-of-issuances", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("KS", "executive_order", "KS library governors", "https://library.ks.gov/kansans/governors", {
        "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("KS", "executive_order", "KS ContentDM Kelly EOs", "https://kslib.info/Archive.aspx?ADID=553", {
        "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("KY", "executive_order", "KY SOS execjournal", "https://web.sos.ky.gov/execjournal/", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
        "browser_wait_selector": "table, form, a[href*='execjournal']",
    }),
    ("KY", "executive_order", "KY SOS execjournal jrnl", "https://web.sos.ky.gov/execjournal/jrnl.aspx", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("NH", "executive_order", "NH SOS exec orders", "https://www.sos.nh.gov/executive-orders", {
        "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("NY", "executive_order", "NY past EOs render_js", "https://www.governor.ny.gov/past-executive-orders", {
        "render_js": True, "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
    ("NY", "executive_order", "NY DOS exec orders", "https://dos.ny.gov/executive-orders", {
        "ignore_robots": True, "user_agent": BROWSER_UA,
    }),
]


def make_source(state: str, ctype: str, name: str, url: str, **kwargs) -> StateSource:
    wait_sel = kwargs.pop("browser_wait_selector", "")
    return StateSource(
        state=state,
        name=name,
        content_type=ctype,
        method="index",
        url=url,
        review_needed=True,
        source_id=f"probe-{state.lower()}-{ctype}-{name[:20].replace(' ', '-')}",
        max_pages=kwargs.pop("max_pages", 1),
        browser_wait_selector=wait_sel,
        **kwargs,
    )


def main() -> None:
    http = HttpFetcher(USER_AGENT, per_domain_delay=0.5)
    browser: BrowserRenderer | None = None
    results = []

    try:
        browser = BrowserRenderer(BROWSER_UA)
        browser.start()

        for state, ctype, name, url, kwargs in CANDIDATES:
            use_browser = browser if kwargs.get("render_js") else None
            src = make_source(state, ctype, name, url, **kwargs)
            row = audit_one_source(src, http, use_browser, min_docs=3)
            row["candidate_name"] = name
            results.append(row)
            print(
                f"{state} {ctype:16} {row['status']:22} eo={row['eo_proc_links']:3} "
                f"bytes={row.get('index_bytes', 0):6} blocked={row.get('blocked_reason', '') or '-':12} "
                f"{name[:45]}"
            )
            for ex in (row.get("examples") or [])[:2]:
                print(f"    ex: {ex['title'][:55]} -> {ex['url'][:75]}")
    finally:
        if browser:
            browser.stop()

    out = ROOT / ".probe_tmp" / "validate_remaining_eo_proc_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
