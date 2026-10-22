#!/usr/bin/env python3
"""Compare Flask /api/v1/sitemap bill paths with Next /sitemap.xml.

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
BILL_PATH = re.compile(r"^/states/[^/]+/bills/")


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


def api_bill_paths() -> tuple[int, set[str]]:
    status, data = get_json("/api/v1/sitemap", API_BASE)
    if status != 200:
        print(f"GET /api/v1/sitemap -> HTTP {status}", file=sys.stderr)
        return -1, set()
    paths = {p for p in data.get("paths") or [] if BILL_PATH.match(p)}
    bill_count = int(data.get("billCount") or len(paths))
    live = int(data.get("liveCount") or 0)
    if bill_count != len(paths):
        print(
            f"Note: billCount={bill_count} vs {len(paths)} bill paths in payload",
            file=sys.stderr,
        )
    if live != bill_count:
        print(
            f"Note: liveCount={live} vs billCount={bill_count} "
            f"(skippedNoSlug={data.get('skippedNoSlug')}, "
            f"skippedNotIndexable={data.get('skippedNotIndexable')})",
            file=sys.stderr,
        )
    return bill_count, paths


def sitemap_bill_paths(xml_text: str) -> set[str]:
    root = ET.fromstring(xml_text)
    locs = [el.text.strip() for el in root.findall("sm:url/sm:loc", NS) if el.text]
    bill_re = re.compile(r"/states/[^/]+/bills/")
    out: set[str] = set()
    for loc in locs:
        if not bill_re.search(loc):
            continue
        # normalize to path only for comparison
        from urllib.parse import urlparse

        out.add(urlparse(loc).path)
    return out


def main() -> int:
    print(f"SMOKE_API_BASE={API_BASE}")
    print(f"SMOKE_SITE_BASE={SITE_BASE}\n")

    api_count, api_paths = api_bill_paths()
    if api_count < 0:
        return 1

    status, xml = get_text("/sitemap.xml", SITE_BASE)
    print(f"GET /sitemap.xml -> HTTP {status}")
    if status != 200:
        print(xml[:500], file=sys.stderr)
        return 1

    site_paths = sitemap_bill_paths(xml)
    print(f"API bill paths:     {api_count}")
    print(f"Sitemap bill URLs:  {len(site_paths)}")

    missing = api_paths - site_paths
    extra = site_paths - api_paths

    if missing:
        print("\nMissing from Next sitemap (first 10):", file=sys.stderr)
        for path in sorted(missing)[:10]:
            print(f"  {path}", file=sys.stderr)
        if len(missing) > 10:
            print(f"  … and {len(missing) - 10} more", file=sys.stderr)

    if extra:
        print("\nExtra in Next sitemap (first 5):", file=sys.stderr)
        for path in sorted(extra)[:5]:
            print(f"  {path}", file=sys.stderr)

    if len(site_paths) < api_count:
        print(
            "\nFAIL: sitemap has fewer bill URLs than API sitemap index.",
            file=sys.stderr,
        )
        print(
            "Tip: restart Next dev server after pulling sitemap fixes; "
            "sitemap.xml is cached ~5 minutes.",
            file=sys.stderr,
        )
        return 1

    if len(site_paths) > api_count + 5:
        print(
            "WARN: sitemap bill URL count exceeds API count by more than 5.",
            file=sys.stderr,
        )

    print("\nOK: sitemap bill coverage matches API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
