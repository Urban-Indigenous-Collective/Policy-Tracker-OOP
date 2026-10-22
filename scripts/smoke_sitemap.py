#!/usr/bin/env python3
"""Compare Live bill count from Flask /api/v1 with bill URLs in Next sitemap.

Requires:
  - Flask: SMOKE_API_BASE (default http://127.0.0.1:5000)
  - Next:  SMOKE_SITE_BASE (default http://127.0.0.1:3000)

Example:
  SMOKE_API_BASE=http://127.0.0.1:5000 SMOKE_SITE_BASE=http://127.0.0.1:3000 \\
    python3 scripts/smoke_sitemap.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

API_BASE = os.getenv("SMOKE_API_BASE", "http://127.0.0.1:5000").rstrip("/")
SITE_BASE = os.getenv("SMOKE_SITE_BASE", "http://127.0.0.1:3000").rstrip("/")

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def get_json(path: str, base: str) -> tuple[int, dict]:
    req = urllib.request.Request(f"{base}{path}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {"raw": body}
        return exc.code, data


def get_text(path: str, base: str) -> tuple[int, str]:
    req = urllib.request.Request(f"{base}{path}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def count_live_bills() -> int:
    status, health = get_json("/api/v1/health", API_BASE)
    if status != 200:
        print(f"GET /api/v1/health -> HTTP {status}", file=sys.stderr)
        return -1
    live = int(health.get("liveCount") or 0)

    status, states = get_json("/api/v1/states", API_BASE)
    if status != 200:
        print(f"GET /api/v1/states -> HTTP {status}", file=sys.stderr)
        return -1

    counted = 0
    codes = list((states.get("states") or {}).keys())
    codes.append("National")
    seen: set[str] = set()
    for code in codes:
        st, data = get_json(f"/api/v1/states/{code}/bills", API_BASE)
        if st != 200:
            continue
        for bill in data.get("bills") or []:
            slug = bill.get("slug")
            if not slug:
                continue
            bill_state = (bill.get("state") or code).strip()
            key = f"{bill_state}:{slug}"
            if key in seen:
                continue
            seen.add(key)
            counted += 1

    if counted != live:
        print(
            f"Note: enumerated {counted} unique bill slugs from state lists "
            f"(health liveCount={live}).",
            file=sys.stderr,
        )
    return counted


def count_sitemap_bill_urls(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    locs = [el.text.strip() for el in root.findall("sm:url/sm:loc", NS) if el.text]
    bill_re = re.compile(r"/states/[^/]+/bills/")
    return [loc for loc in locs if bill_re.search(loc)]


def main() -> int:
    print(f"SMOKE_API_BASE={API_BASE}")
    print(f"SMOKE_SITE_BASE={SITE_BASE}\n")

    api_bills = count_live_bills()
    if api_bills < 0:
        return 1

    status, xml = get_text("/sitemap.xml", SITE_BASE)
    print(f"GET /sitemap.xml -> HTTP {status}")
    if status != 200:
        print(xml[:500], file=sys.stderr)
        return 1

    bill_urls = count_sitemap_bill_urls(xml)
    print(f"API bill rows (unique slugs): {api_bills}")
    print(f"Sitemap bill URLs:           {len(bill_urls)}")

    if len(bill_urls) < api_bills:
        print(
            "FAIL: sitemap has fewer bill URLs than API Live bills.",
            file=sys.stderr,
        )
        return 1

    if len(bill_urls) > api_bills + 5:
        print(
            "WARN: sitemap bill URL count exceeds API count by more than 5 "
            "(possible duplicates or stale data).",
            file=sys.stderr,
        )

    print("\nOK: sitemap bill coverage looks consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
