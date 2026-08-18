#!/usr/bin/env python3
"""Extended validation for Vermont legislature sources (Playwright required)."""

import json
import sys
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from discovery.site_crawler import StateSiteSource
from validate_state_sources import check_source

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA = "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)"
VT_MANIFEST = ROOT / "sources" / "manifests" / "VT.json"


def tls_diagnostics():
    print("=== TLS diagnostics ===")
    import ssl
    import socket

    host = "legislature.vermont.gov"
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                print(f"Cert OK with default verify: {cert.get('subject')}")
    except ssl.SSLError as exc:
        print(f"Default TLS verify FAILS (expected): {exc}")
        print("  -> VT site omits GlobalSign intermediate cert; manifests use ssl_verify=false")


def sample_bill_page():
    print("\n=== Sample bill page (direct URL) ===")
    url = "https://legislature.vermont.gov/bill/status/2026/H.121"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20, verify=False)
    print(f"GET {url} -> {r.status_code}, {len(r.text)} bytes")
    if "act relating" in r.text.lower():
        print("  Bill title HTML present (server-rendered)")


def main():
    load_dotenv(ROOT / ".env")
    tls_diagnostics()
    sample_bill_page()

    data = json.loads(VT_MANIFEST.read_text())
    sources = data["sources"]
    print(f"\n=== Manifest smoke tests ({len(sources)} sources) ===")
    from discovery.source_schema import StateSource

    for raw in sources:
        source = StateSource.model_validate(raw)
        ok, detail = check_source(source)
        print(f"[{'OK' if ok else 'FAIL'}] {source.name} -> {detail}")

    print("\n=== Browser crawl dry-run ===")
    print("(requires: pip install playwright && playwright install chromium)")
    temp = ROOT / "sources" / ".vt_test.json"
    temp.write_text(json.dumps({"sources": sources}), encoding="utf-8")

    from discovery.browser_fetcher import BrowserRenderer
    from discovery.fetchers import HttpFetcher, _fetch_html

    http = HttpFetcher(UA, per_domain_delay=0.5)
    browser = BrowserRenderer(UA)
    try:
        for raw in sources:
            source = StateSource.model_validate(raw)
            query_note = ""
            if source.method == "search":
                demo_query = "indigenous"
                html, _ = _fetch_html(
                    http,
                    browser,
                    source,
                    source.search_url,
                    query=demo_query,
                )
                base = source.search_url
                query_note = f" (demo query: {demo_query!r})"
            else:
                html, _ = _fetch_html(http, browser, source, source.url)
                base = source.url
            raw_links = http.extract_links(
                base,
                html,
                same_domain_only=False,
                link_selector=source.link_selector,
                link_context_parent="tr" if source.link_selector else None,
            )
            print(f"  {source.name}: {len(raw_links)} bill link(s) rendered{query_note if source.method == 'search' else ''}")
            if raw_links[:2]:
                print(f"    e.g. {raw_links[0][1]} -> {raw_links[0][0]}")
    finally:
        browser.stop()

    crawler = StateSiteSource(sources_path=temp, per_domain_delay=0.5)
    prescreen = 0
    for candidate in crawler.discover():
        prescreen += 1
        print(f"  MMIP candidate: {candidate.title[:70]!r} -> {candidate.url[:80]}")
    print(f"Bill links after MMIP prescreen: {prescreen}")
    temp.unlink(missing_ok=True)

    print("\n=== Notes ===")
    print("- VT legislature list/search pages are JS-rendered (DataTables); use render_js sources.")
    print("- State legislature sites are crawled directly — not via LegiScan.")
    print("- Update session year (2026) in manifest URLs each biennium.")
    print("- Production: unset PLAYWRIGHT_BROWSERS_PATH if sandbox pointed at wrong arch.")


if __name__ == "__main__":
    main()
