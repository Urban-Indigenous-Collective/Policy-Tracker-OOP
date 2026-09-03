#!/usr/bin/env python3
"""Add state Attorney General press rooms to MMIP crawl manifests.

Governor / legislature / SOS indexes never see AG appointments, MMIP task-force
staffing, or AG-issued MMIP policy. This bootstrap probes curated listing URLs
from sources/ag_hosts.json and writes enabled press_release sources.

Usage:
  python scripts/bootstrap_ag_sources.py --dry-run
  python scripts/bootstrap_ag_sources.py --states SD --apply
  python scripts/bootstrap_ag_sources.py --all --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.ag_coverage import load_ag_hosts, url_matches_ag  # noqa: E402
from discovery.source_schema import StateManifest, StateSource, load_sources_data  # noqa: E402

MANIFESTS_DIR = ROOT / "sources" / "manifests"
REPORT_PATH = ROOT / "sources" / "ag_bootstrap_report.md"

USER_AGENT = "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
PROBE_TIMEOUT = 25
MIN_BODY_BYTES = 800
DISCOVERED_BY = "ag_bootstrap_2026_09"

FALLBACK_PATHS = (
    "/news",
    "/news/",
    "/newsroom",
    "/press-releases",
    "/press-releases/",
    "/media",
    "/media/press-releases",
    "/news-releases",
    "/press",
    "/releases",
    "/news/press-releases",
)


def load_manifest(state: str) -> StateManifest:
    path = MANIFESTS_DIR / f"{state}.json"
    if not path.exists():
        return StateManifest(state=state, sources=[])
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return StateManifest(state=state, sources=load_sources_data(data))


def append_source(state: str, source: StateSource) -> None:
    """Append one source without rewriting the rest of the manifest."""
    path = MANIFESTS_DIR / f"{state}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"state": state, "sources": []}
    data.setdefault("sources", []).append(source.model_dump())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def existing_ag_source(manifest: StateManifest, state: str, hosts: dict) -> StateSource | None:
    for source in manifest.sources:
        if url_matches_ag(state, source.primary_url(), hosts):
            return source
    return None


def _probe_once(url: str, user_agent: str) -> tuple[bool, str, str]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": user_agent},
            timeout=PROBE_TIMEOUT,
            allow_redirects=True,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:80]}", user_agent

    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}", user_agent
    body = response.text or ""
    if len(body) < MIN_BODY_BYTES:
        return False, f"body too small ({len(body)} bytes)", user_agent
    lowered = body[:4000].lower()
    if "page not found" in lowered or "404 error" in lowered:
        return False, "soft 404", user_agent
    final = urlparse(response.url)
    wanted = urlparse(url)
    if wanted.path.rstrip("/") and final.path.rstrip("/") in ("", "/"):
        return False, f"redirected to root ({response.url})", user_agent
    return True, f"HTTP {response.status_code}, {len(body)} bytes", user_agent


def probe_url(url: str) -> tuple[bool, str, str]:
    ok, detail, ua = _probe_once(url, USER_AGENT)
    if ok:
        return ok, detail, ua
    if "403" in detail:
        return _probe_once(url, BROWSER_USER_AGENT)
    return ok, detail, ua


def candidate_urls(entry: dict) -> list[str]:
    urls: list[str] = []
    listing = str(entry.get("listing_url") or "").strip()
    if listing:
        urls.append(listing)
    host = str(entry.get("host") or "").strip()
    prefix = str(entry.get("path_prefix") or "").rstrip("/")
    if host:
        origin = f"https://{host.removeprefix('www.')}"
        base = f"{origin}{prefix}" if prefix else origin
        for path in FALLBACK_PATHS:
            urls.append(base.rstrip("/") + path)
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        ordered.append(url)
    return ordered


def to_source(
    state: str,
    url: str,
    entry: dict,
    user_agent: str,
    *,
    curated: bool,
    review_needed: bool = False,
) -> StateSource:
    notes = str(entry.get("notes") or "").strip()
    extra = "Curated AG press index." if curated else "AG press path found by host template probe."
    if review_needed:
        extra = "Probe failed from bootstrap host; listing URL recorded for prod verification. " + extra
    notes = f"{notes} | {extra}".strip(" |")
    kwargs: dict = {
        "state": state,
        "name": f"{state} — Attorney General press releases",
        "content_type": "press_release",
        "method": "index",
        "url": url,
        "review_needed": review_needed,
        "discovered_by": DISCOVERED_BY,
        "discovered_on": date.today().isoformat(),
        "notes": notes,
        "confidence": "low" if review_needed else ("high" if curated else "medium"),
        "user_agent": "" if user_agent == USER_AGENT else user_agent,
        "ignore_robots": user_agent != USER_AGENT,
    }
    if state == "SD":
        kwargs["link_selector"] = "a[href*='pressreleasesdetail']"
        kwargs["max_pages"] = 3
    return StateSource(**kwargs)


def bootstrap_state(state: str, entry: dict, hosts: dict) -> dict:
    manifest = load_manifest(state)
    existing = existing_ag_source(manifest, state, hosts)
    if existing:
        return {
            "state": state,
            "status": "already_present",
            "url": existing.primary_url(),
            "name": existing.name,
            "manifest": manifest,
        }

    failures: list[str] = []
    listing = str(entry.get("listing_url") or "").strip()
    for url in candidate_urls(entry):
        ok, detail, ua = probe_url(url)
        if not ok:
            failures.append(f"{url} — {detail}")
            continue
        curated = bool(listing) and url.rstrip("/") == listing.rstrip("/")
        source = to_source(state, url, entry, ua, curated=curated)
        return {
            "state": state,
            "status": "added",
            "url": url,
            "detail": detail,
            "curated": curated,
            "source": source,
            "failures": failures,
        }

    return {
        "state": state,
        "status": "failed",
        "url": listing,
        "failures": failures,
        "source": to_source(
            state, listing, entry, USER_AGENT, curated=True, review_needed=True
        )
        if listing
        else None,
    }


def write_report(results: list[dict]) -> None:
    added = [r for r in results if r["status"] == "added"]
    present = [r for r in results if r["status"] == "already_present"]
    failed = [r for r in results if r["status"] == "failed"]
    lines = [
        "# Attorney General Source Bootstrap",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "## Summary",
        "",
        f"- States processed: {len(results)}",
        f"- AG sources added: {len(added)}",
        f"- Already covered: {len(present)}",
        f"- Probe failed: {len(failed)}",
        "",
        "## Added",
        "",
    ]
    for row in added:
        lines.append(f"- **{row['state']}** {row['url']} ({row.get('detail', '')})")
    if not added:
        lines.append("_None_")
    lines.extend(["", "## Already covered", ""])
    for row in present:
        lines.append(f"- **{row['state']}** {row['url']} (`{row.get('name', '')}`)")
    if not present:
        lines.append("_None_")
    lines.extend(["", "## Failed probes", ""])
    for row in failed:
        lines.append(f"- **{row['state']}**")
        for fail in row.get("failures") or []:
            lines.append(f"  - {fail}")
    if not failed:
        lines.append("_None_")
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap state AG press sources")
    parser.add_argument("--states", nargs="*", help="State codes to process")
    parser.add_argument("--all", action="store_true", help="Process every AG host")
    parser.add_argument("--apply", action="store_true", help="Write manifest changes")
    parser.add_argument("--dry-run", action="store_true", help="Probe without writing")
    args = parser.parse_args()

    hosts = load_ag_hosts()
    if args.all:
        states = sorted(hosts)
    elif args.states:
        states = [s.upper() for s in args.states]
    else:
        parser.error("pass --states or --all")

    results: list[dict] = []
    for state in states:
        entry = hosts.get(state)
        if not entry:
            print(f"[{state}] no AG host map entry")
            continue
        result = bootstrap_state(state, entry, hosts)
        results.append(result)
        status = result["status"]
        url = result.get("url") or ""
        print(f"[{state}] {status} {url}".rstrip())
        if args.apply and status == "added":
            append_source(state, result["source"])
        if args.apply and status == "failed" and result.get("source"):
            append_source(state, result["source"])
            print(f"  recorded review_needed listing {result['url']}")

    write_report(results)
    print(f"\nReport written to {REPORT_PATH}")
    failed_n = sum(1 for r in results if r["status"] == "failed")
    if failed_n:
        print(f"{failed_n} state(s) still need a working AG listing URL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
