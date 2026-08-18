#!/usr/bin/env python3
"""Ground-truth audit: do EO/proclamation index URLs return document-shaped links?

Crawl-only — no LLM, no Airtable, no MMIP prescreen. For each enabled
executive_order / proclamation source (review_needed=false), fetch up to
max_pages, classify extracted links, and flag broken or off-target endpoints.

Usage:
  .venv/bin/python scripts/audit_eo_proc_endpoints.py
  .venv/bin/python scripts/audit_eo_proc_endpoints.py --state NC --workers 2
  .venv/bin/python scripts/audit_eo_proc_endpoints.py --apply-quarantine
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.browser_fetcher import BrowserRenderer, looks_like_bot_wall  # noqa: E402
from discovery.fetchers import (  # noqa: E402
    HttpFetcher,
    IndexFetcher,
    _fetch_html,
    extract_table_document_links,
    next_page_url,
)
from discovery.source_schema import StateSource, load_sources_data  # noqa: E402
from discovery.url_utils import normalize_url  # noqa: E402

logger = logging.getLogger(__name__)

PROBE_DIR = ROOT / ".probe_tmp"
STATE_SOURCES_PATH = ROOT / "sources" / "state_sources.json"
MANIFESTS_DIR = ROOT / "sources" / "manifests"

USER_AGENT = (
    "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org; eo-proc-endpoint-audit)"
)

EO_PROC_CONTENT_TYPES = ("executive_order", "proclamation")
STATUSES = ("OK", "ZERO_DOCS", "WRONG_CONTENT_TYPE", "QUARANTINE_CANDIDATE", "BLOCKED", "THIN")

# --- Link / page heuristics (no MMIP) ---------------------------------------

EO_PROC_URL_RE = re.compile(
    r"executive[-_ ]order|/eo[-/]|/executive[-_]orders?/|administrative[-_ ]order|"
    r"proclamation|/procs?/|/proclamations?/|/declarations?/|"
    r"View\?doc=|viewdocument|/documents/governor|sos\.mo\.gov/library|"
    r"publications\.tnsosfiles\.com|govdocs\.|infobank\.|"
    r"\.pdf(?:$|[?#])|drive\.google\.com",
    re.IGNORECASE,
)

EO_PROC_TEXT_RE = re.compile(
    r"\bexecutive\s+order\b|\bproclamation\b|\badministrative\s+order\b|"
    r"\bdeclaration\b|\bemergency\s+proclamation\b|"
    r"\b(?:EO|E\.O\.)\s*#?\s*\d|\bExecutive Order No\.?\s*\d|"
    r"\bProclamation\s+\d|\bOrder\s+\d{4}-\d+",
    re.IGNORECASE,
)

EO_NUMBER_RE = re.compile(
    r"\b(?:EO|E\.O\.|Executive Order|Administrative Order|Proclamation)\s*#?\s*[\d-]+",
    re.IGNORECASE,
)

GENERIC_NAV_RE = re.compile(
    r"^(?:home|about|contact|news|newsroom|press releases?|services|search|login|"
    r"subscribe|privacy|accessibility|sitemap|menu|skip to content)$",
    re.IGNORECASE,
)

NEWS_PRESS_RE = re.compile(
    r"\bpress release\b|\bnews release\b|\bnewsroom\b|\bannouncement\b|"
    r"\bbudget\b|\blegislative session\b|\bbill signing\b",
    re.IGNORECASE,
)

SOFT_404_RE = re.compile(
    r"page not found|404\b|not found|does not exist|no longer available|"
    r"we couldn't find|couldn't find that page",
    re.IGNORECASE,
)

HOMEPAGE_PATHS = frozenset({"", "/", "/index.html", "/index.htm", "/home", "/home/"})


def classify_link(
    url: str,
    title: str,
    context: str,
    expected_type: str,
    index_url: str = "",
) -> str:
    """Return 'eo_proc', 'other', or 'nav'."""
    norm_url = normalize_url(url)
    norm_index = normalize_url(index_url) if index_url else ""
    title_stripped = title.strip()

    # Section index self-links and EO↔proc cross-nav tabs.
    if norm_index and norm_url == norm_index:
        return "nav"
    if title_stripped.lower() in (
        "proclamations",
        "executive orders",
        "executive order",
        "administrative orders",
        "declarations",
        "emergency proclamations",
    ) and re.search(r"/(proclamations?|executive[-_]orders?|procs|declarations?)(?:/|$)", url, re.I):
        return "nav"
    if title_stripped.lower() in ("request a proclamation", "proclamation request form"):
        return "nav"

    blob = f"{url}\n{title}\n{context}".strip()

    # Maryland-style governor media detail pages listed on proc/EO indexes.
    if re.search(r"governor\.[a-z.]+\.(gov|us)/media/\d+", url, re.I):
        return "eo_proc"
    # NC/Drupal governor article slugs from proclamation indexes.
    if expected_type == "proclamation" and re.search(
        r"governor\.[a-z.]+\.(gov|us)/governor-[\w-]*proclaim", url, re.I
    ):
        return "eo_proc"
    if re.search(r"\bproclaims?\b", blob, re.I):
        return "eo_proc"

    if GENERIC_NAV_RE.match(title_stripped):
        return "nav"
    if EO_PROC_URL_RE.search(url) or EO_PROC_TEXT_RE.search(blob) or EO_NUMBER_RE.search(blob):
        return "eo_proc"
    if NEWS_PRESS_RE.search(blob) and not EO_PROC_TEXT_RE.search(blob):
        return "other"
    # Weak titles on document hosts still count when URL looks archival.
    if expected_type == "executive_order" and re.search(
        r"executive|administrative.?order|/eo", url, re.I
    ):
        return "eo_proc"
    if expected_type == "proclamation" and re.search(
        r"proclamation|procs?/|declaration", url, re.I
    ):
        return "eo_proc"
    if len(title_stripped) < 4 and EO_PROC_URL_RE.search(url):
        return "eo_proc"
    return "other"


def page_title(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.S)
    return (m.group(1).strip() if m else "")[:200]


def looks_like_homepage_redirect(configured_url: str, final_url: str, html: str) -> bool:
    if not final_url:
        return False
    cfg = urlparse(configured_url)
    fin = urlparse(final_url)
    cfg_path = cfg.path.rstrip("/").lower()
    fin_path = fin.path.rstrip("/").lower()
    if fin_path in HOMEPAGE_PATHS and cfg_path not in HOMEPAGE_PATHS:
        return True
    # Request form / engagement pages masquerading as archives.
    if re.search(r"request|form|engage|contact", fin_path) and "proclamation" in cfg_path:
        return True
    title = page_title(html).lower()
    if "request a proclamation" in title or "proclamation request" in title:
        return True
    return False


def audit_one_source(
    source: StateSource,
    http: HttpFetcher,
    browser: BrowserRenderer | None,
    min_docs: int,
) -> dict[str, Any]:
    started = time.time()
    index_url = source.primary_url()
    all_links: list[dict[str, str]] = []
    pages_fetched = 0
    fetch_error = ""
    blocked_reason = ""
    final_index_url = ""
    index_bytes = 0
    repeated_page = False

    max_pages = max(1, int(source.max_pages or 1))
    template = source.page_url_template or ""
    selector = source.next_page_selector or ""
    extra_domains = list(source.allowed_extra_domains or [])
    context_parent = "tr" if source.link_selector else None
    visited: set[str] = set()
    seen_hashes: set[str] = set()
    seen_texts: set[str] = set()
    url = source.url

    for page_no in range(1, max_pages + 1):
        if template and page_no > 1:
            url = template.replace("{page}", str(page_no))
        norm = normalize_url(url)
        if norm in visited:
            break
        visited.add(norm)

        html, content_hash, final_url = _fetch_html(http, browser, source, url)
        if not html:
            if page_no == 1:
                fetch_error = "empty_response"
            break
        if page_no == 1:
            final_index_url = final_url or url
            index_bytes = len(html.encode("utf-8", errors="replace"))
            if looks_like_bot_wall(html):
                blocked_reason = "bot_wall"
                break
            if SOFT_404_RE.search(page_title(html)):
                blocked_reason = "soft_404_title"
            elif index_bytes < 1200 and len(html) < 2000:
                blocked_reason = "tiny_body"
            elif looks_like_homepage_redirect(index_url, final_index_url, html):
                blocked_reason = "homepage_redirect"

        if content_hash and content_hash in seen_hashes:
            repeated_page = True
            break
        seen_hashes.add(content_hash)
        pages_fetched += 1

        link_base = final_url or url
        raw_links = http.extract_links(
            link_base,
            html,
            same_domain_only=True,
            link_selector=source.link_selector,
            link_context_parent=context_parent,
            allowed_extra_domains=extra_domains,
        )
        template = getattr(source, "document_url_template", "") or ""
        if template:
            seen_link_urls = {link_url for link_url, _text, _ctx in raw_links}
            for link_url, link_text, link_context in extract_table_document_links(html, template):
                if link_url not in seen_link_urls:
                    raw_links.append((link_url, link_text, link_context))
                    seen_link_urls.add(link_url)
        page_texts = {text for _u, text, _c in raw_links}
        if page_no > 1 and page_texts and not (page_texts - seen_texts):
            repeated_page = True
            break
        seen_texts |= page_texts

        for link_url, link_text, link_context in raw_links:
            kind = classify_link(
                link_url, link_text, link_context, source.content_type, index_url
            )
            all_links.append(
                {
                    "url": link_url,
                    "title": (link_text or "")[:200],
                    "context": (link_context or "")[:200],
                    "kind": kind,
                    "page": page_no,
                }
            )

        eo_count = sum(1 for lk in all_links if lk["kind"] == "eo_proc")
        if eo_count >= min_docs:
            break

        if page_no >= max_pages or template:
            continue
        nxt = next_page_url(url, html, selector)
        if not nxt:
            break
        url = nxt

    counts = {"eo_proc": 0, "other": 0, "nav": 0}
    seen_urls: set[str] = set()
    eo_examples: list[dict[str, str]] = []
    for lk in all_links:
        norm = normalize_url(lk["url"])
        if norm in seen_urls:
            continue
        seen_urls.add(norm)
        counts[lk["kind"]] += 1
        if lk["kind"] == "eo_proc" and len(eo_examples) < 5:
            eo_examples.append({"url": lk["url"], "title": lk["title"]})

    status, detail = determine_status(
        source=source,
        counts=counts,
        pages_fetched=pages_fetched,
        min_docs=min_docs,
        blocked_reason=blocked_reason,
        fetch_error=fetch_error,
        repeated_page=repeated_page,
        index_bytes=index_bytes,
        total_links=len(seen_urls),
    )

    return {
        "source_id": source.source_id,
        "state": source.state,
        "name": source.name,
        "content_type": source.content_type,
        "url": index_url,
        "final_url": final_index_url or index_url,
        "max_pages": max_pages,
        "pages_fetched": pages_fetched,
        "index_bytes": index_bytes,
        "total_links": len(seen_urls),
        "eo_proc_links": counts["eo_proc"],
        "other_links": counts["other"],
        "nav_links": counts["nav"],
        "status": status,
        "detail": detail,
        "blocked_reason": blocked_reason,
        "fetch_error": fetch_error,
        "repeated_pagination": repeated_page,
        "examples": eo_examples,
        "elapsed_s": round(time.time() - started, 1),
    }


def determine_status(
    *,
    source: StateSource,
    counts: dict[str, int],
    pages_fetched: int,
    min_docs: int,
    blocked_reason: str,
    fetch_error: str,
    repeated_page: bool,
    index_bytes: int,
    total_links: int,
) -> tuple[str, str]:
    if blocked_reason:
        if blocked_reason == "bot_wall":
            return "BLOCKED", "Bot wall / access denied on index page"
        if blocked_reason == "homepage_redirect":
            return "QUARANTINE_CANDIDATE", "Index URL redirects to homepage or request form"
        if blocked_reason == "soft_404_title":
            return "QUARANTINE_CANDIDATE", "Page title indicates 404 / not found"
        if blocked_reason == "tiny_body":
            return "QUARANTINE_CANDIDATE", f"Tiny response body ({index_bytes} bytes) — likely soft-404 shell"
    if fetch_error and pages_fetched == 0:
        return "BLOCKED", f"Could not fetch index: {fetch_error}"
    if pages_fetched == 0:
        return "BLOCKED", "Zero pages fetched"
    if counts["eo_proc"] == 0 and total_links == 0:
        return "ZERO_DOCS", "Index fetched but zero extractable links"
    if counts["eo_proc"] == 0 and total_links >= 5:
        return "WRONG_CONTENT_TYPE", (
            f"{total_links} links but none EO/proc-shaped — likely news/nav only"
        )
    if counts["eo_proc"] == 0:
        return "ZERO_DOCS", f"{total_links} links, none EO/proc-shaped"
    if counts["eo_proc"] < min_docs:
        return "THIN", f"Only {counts['eo_proc']} EO/proc-like link(s) (need ≥{min_docs})"
    if repeated_page and source.max_pages > 1 and counts["eo_proc"] < min_docs:
        return "THIN", "Pagination repeats page 1; shallow yield"
    return "OK", f"{counts['eo_proc']} EO/proc-like links across {pages_fetched} page(s)"


def load_no_ground_truth_states() -> set[str]:
    """Best-effort from latest Main v3 EO/proc completeness artifact."""
    candidates = sorted(PROBE_DIR.glob("main_v3_eo_proc_completeness_*.json"), reverse=True)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data.get("no_ground_truth_states") or []
            if rows:
                return {r["state"] for r in rows}
        except Exception:
            continue
    return set()


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    s = payload["summary"]
    lines = [
        "# EO/Proclamation Endpoint Audit",
        "",
        f"Generated: {payload['generated_at']}",
        f"Elapsed: {payload['elapsed_seconds']}s",
        "",
        "## Verdict",
        "",
        payload.get("verdict", ""),
        "",
        "## Summary",
        "",
        f"- **Sources audited:** {s['total_sources']}",
        f"- **OK:** {s['by_status'].get('OK', 0)}",
        f"- **Thin (<{payload['min_docs']} docs):** {s['by_status'].get('THIN', 0)}",
        f"- **Zero docs:** {s['by_status'].get('ZERO_DOCS', 0)}",
        f"- **Wrong content type:** {s['by_status'].get('WRONG_CONTENT_TYPE', 0)}",
        f"- **Quarantine candidate:** {s['by_status'].get('QUARANTINE_CANDIDATE', 0)}",
        f"- **Blocked:** {s['by_status'].get('BLOCKED', 0)}",
        f"- **No Main v3 ground truth states:** {s['no_ground_truth_state_count']}",
        f"- **No-ground-truth OK rate:** {s.get('no_gt_ok_rate', '—')}",
        "",
        "## Per-source results",
        "",
        "| State | Source | Type | Status | Pages | EO/proc | Total | Detail |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for r in payload["results"]:
        lines.append(
            f"| {r['state']} | `{r['source_id']}` | {r['content_type']} | "
            f"**{r['status']}** | {r['pages_fetched']} | {r['eo_proc_links']} | "
            f"{r['total_links']} | {r['detail'][:80]} |"
        )

    examples = [r for r in payload["results"] if r.get("examples")]
    if examples:
        lines.extend(["", "## Sample EO/proc links", ""])
        for r in examples:
            if not r["examples"]:
                continue
            lines.append(f"### {r['state']} — {r['source_id']} ({r['status']})")
            for ex in r["examples"][:3]:
                lines.append(f"- {ex['title'][:100]} — {ex['url']}")
            lines.append("")

    broken = [r for r in payload["results"] if r["status"] not in ("OK", "THIN")]
    if broken:
        lines.extend(["", "## Broken / off-target endpoints", ""])
        for r in broken:
            lines.append(f"- **{r['state']}** `{r['source_id']}` — **{r['status']}**: {r['detail']}")
            lines.append(f"  - URL: {r['url']}")
            if r.get("final_url") and r["final_url"] != r["url"]:
                lines.append(f"  - Final: {r['final_url']}")

    if payload.get("quarantine_applied"):
        lines.extend(["", "## Quarantine / fixes applied", ""])
        for fix in payload["quarantine_applied"]:
            lines.append(f"- {fix}")

    lines.extend(["", "## Artifacts", "", f"- JSON: `{payload['json_path']}`", f"- Markdown: `{path}`"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compute_verdict(results: list[dict], no_gt_states: set[str]) -> str:
    no_gt_results = [r for r in results if r["state"] in no_gt_states]
    no_gt_ok = [r for r in no_gt_results if r["status"] == "OK"]
    no_gt_broken = [
        r for r in no_gt_results if r["status"] in ("ZERO_DOCS", "WRONG_CONTENT_TYPE", "QUARANTINE_CANDIDATE", "BLOCKED")
    ]

    all_ok = sum(1 for r in results if r["status"] == "OK")
    all_broken = sum(1 for r in results if r["status"] in ("ZERO_DOCS", "WRONG_CONTENT_TYPE", "QUARANTINE_CANDIDATE", "BLOCKED"))

    if not no_gt_results:
        base = f"**{all_ok}/{len(results)} sources OK** overall."
    else:
        rate = round(100 * len(no_gt_ok) / len(no_gt_results)) if no_gt_results else 0
        base = (
            f"**{len(no_gt_ok)}/{len(no_gt_results)} ({rate}%) OK** among states without Main v3 "
            f"EO/proc ground truth; **{all_ok}/{len(results)} OK** overall."
        )

    if not no_gt_broken and all_broken == 0:
        return f"**Solid.** {base} All audited endpoints return EO/proc-shaped document links."
    if len(no_gt_broken) <= 3 and len(no_gt_ok) >= len(no_gt_broken) * 2:
        broken_ids = ", ".join(f"{r['state']}:{r['source_id']}" for r in no_gt_broken[:5])
        return f"**Mostly solid.** {base} Broken/off-target: {broken_ids}."
    broken_ids = ", ".join(f"{r['state']}:{r['status']}" for r in no_gt_broken[:8])
    return f"**Gaps remain.** {base} Issues: {broken_ids}."


def apply_quarantine(results: list[dict], audit_ts: str) -> list[str]:
    """Set review_needed=true on clearly broken sources in per-state manifests."""
    quarantine_statuses = {"QUARANTINE_CANDIDATE", "WRONG_CONTENT_TYPE", "ZERO_DOCS", "BLOCKED"}
    fixes: list[str] = []
    by_id = {r["source_id"]: r for r in results if r["status"] in quarantine_statuses}

    for path in sorted(MANIFESTS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        sources = raw.get("sources") if isinstance(raw, dict) else raw
        if not isinstance(sources, list):
            continue
        changed = False
        for src in sources:
            sid = src.get("source_id") or ""
            hit = by_id.get(sid)
            if not hit or src.get("review_needed"):
                continue
            note = (
                f"endpoint audit {audit_ts}: {hit['status']} — {hit['detail']}"
            )
            existing = (src.get("notes") or "").strip()
            src["review_needed"] = True
            src["notes"] = f"{existing} | {note}".strip(" |") if existing else note
            changed = True
            fixes.append(f"{sid} -> review_needed=true ({hit['status']})")
        if changed:
            path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return fixes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", default=str(STATE_SOURCES_PATH))
    parser.add_argument("--state", default="", help="Optional two-letter filter")
    parser.add_argument("--source-id", default="", help="Optional single source_id")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=1.0, help="Per-domain delay seconds")
    parser.add_argument("--min-docs", type=int, default=3, help="Minimum EO/proc-like links for OK")
    parser.add_argument("--apply-quarantine", action="store_true", help="Quarantine broken sources in manifests")
    parser.add_argument("--merge", action="store_true", help="Run merge_state_manifests after quarantine")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    started = time.time()

    raw = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    all_sources = load_sources_data(raw)
    selected = [
        s
        for s in all_sources
        if s.content_type in EO_PROC_CONTENT_TYPES
        and not s.review_needed
        and s.method == "index"
        and (not args.state or s.state == args.state.upper())
        and (not args.source_id or s.source_id == args.source_id)
    ]
    selected.sort(key=lambda s: (s.state, s.source_id))

    no_gt_states = load_no_ground_truth_states()
    needs_browser = any(s.render_js for s in selected)

    print(f"Auditing {len(selected)} EO/proc index sources ({args.workers} workers, delay={args.delay}s)")

    def run_one(source: StateSource) -> dict[str, Any]:
        http = HttpFetcher(USER_AGENT, per_domain_delay=args.delay)
        browser = BrowserRenderer(USER_AGENT) if source.render_js else None
        if browser:
            browser.start()
        try:
            return audit_one_source(source, http, browser, args.min_docs)
        finally:
            if browser:
                browser.stop()

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, s): s for s in selected}
        for i, fut in enumerate(as_completed(futures), start=1):
            row = fut.result()
            row["has_main_v3_ground_truth"] = row["state"] not in no_gt_states
            results.append(row)
            print(
                f"  [{i}/{len(selected)}] {row['source_id']:45} "
                f"{row['status']:22} eo={row['eo_proc_links']:3} pages={row['pages_fetched']}"
            )

    results.sort(key=lambda r: (r["state"], r["source_id"]))
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    no_gt_results = [r for r in results if r["state"] in no_gt_states]
    no_gt_ok = sum(1 for r in no_gt_results if r["status"] == "OK")
    no_gt_rate = (
        f"{no_gt_ok}/{len(no_gt_results)} ({round(100 * no_gt_ok / len(no_gt_results))}%)"
        if no_gt_results
        else "—"
    )

    elapsed = round(time.time() - started, 1)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    json_path = PROBE_DIR / f"eo_proc_endpoint_audit_{ts}.json"
    md_path = PROBE_DIR / f"eo_proc_endpoint_audit_{ts}.md"

    quarantine_applied: list[str] = []
    if args.apply_quarantine:
        quarantine_applied = apply_quarantine(results, ts[:8])
        if quarantine_applied and args.merge:
            import subprocess

            subprocess.run(
                [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "merge_state_manifests.py")],
                check=True,
                cwd=ROOT,
            )
            quarantine_applied.append("merged state_sources.json via merge_state_manifests.py")

    verdict = compute_verdict(results, no_gt_states)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "methodology": {
            "filter": "enabled executive_order + proclamation, review_needed=false, method=index",
            "mmip_prescreen": "disabled — raw link heuristics only",
            "min_docs_for_ok": args.min_docs,
            "early_stop": "after min_docs eo_proc links found",
            "workers": args.workers,
            "delay": args.delay,
        },
        "verdict": verdict,
        "min_docs": args.min_docs,
        "summary": {
            "total_sources": len(results),
            "by_status": by_status,
            "no_ground_truth_state_count": len(no_gt_states),
            "no_ground_truth_sources": len(no_gt_results),
            "no_gt_ok_rate": no_gt_rate,
        },
        "no_ground_truth_states": sorted(no_gt_states),
        "results": results,
        "quarantine_applied": quarantine_applied,
        "json_path": str(json_path),
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_path, payload)

    print(f"\n{verdict}")
    print(f"Status counts: {by_status}")
    print(f"Wrote {json_path}\nWrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
