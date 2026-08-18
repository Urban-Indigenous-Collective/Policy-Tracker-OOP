#!/usr/bin/env python3
"""Main v3 state EO/proclamation completeness audit (read-only Airtable).

Filters non-LegiScan Main v3 rows to executive orders and proclamations, then
runs the fast reachability heuristics against enabled EO/proc state sources
(and related governor-news proclamation channels).

Usage:
  .venv/bin/python scripts/audit_eo_proc_completeness.py
  .venv/bin/python scripts/audit_eo_proc_completeness.py --skip-crawl
  .venv/bin/python scripts/audit_eo_proc_completeness.py --state NC
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_main_v3_reachability as _reach  # noqa: E402

from airtable_client import AirtableClient  # noqa: E402
from discovery.fetchers import HttpFetcher  # noqa: E402
from discovery.source_schema import DEFAULT_MAX_PAGES, StateSource, load_sources_data  # noqa: E402
from discovery.url_utils import normalize_url  # noqa: E402

logger = logging.getLogger(__name__)

PROBE_DIR = ROOT / ".probe_tmp"
STATE_SOURCES_PATH = ROOT / "sources" / "state_sources.json"
USER_AGENT = _reach.USER_AGENT
URL_FIELDS = _reach.URL_FIELDS
LEGISCAN_RE = _reach.LEGISCAN_RE
YEAR_IN_SLUG_RE = _reach.YEAR_IN_SLUG_RE

FEDERAL_HOSTS = re.compile(
    r"(whitehouse\.gov|justice\.gov|federalregister\.gov|congress\.gov)", re.I
)
LEGIS_BILL = re.compile(r"^(HB|SB|AB|LB|SJR|SR|HR|SM|HCR|SCR)\b", re.I)
LEGIS_URL = re.compile(
    r"(legislature|legis\.|/leg/|nmlegis|legislation\.nysenate|leg\.colorado|leg\.wa\.gov|legis\.wisconsin|sdlegislature|utah\.gov/~)",
    re.I,
)

EO_PROC_CONTENT_TYPES = ("executive_order", "proclamation")
# Governor news / DOA press used when no public proclamation archive exists.
PROC_CHANNEL_TYPES = ("press_release",)
PROC_CHANNEL_NOTES = re.compile(r"proclamation|MMIP awareness|announcement channel", re.I)


def _extract_year(url: str, title: str = "") -> str | None:
    for text in (url, title):
        m = YEAR_IN_SLUG_RE.search(text)
        if m:
            return m.group(1)
    return None


def classify_eo_proc_record(fields: dict, url: str) -> tuple[str | None, str]:
    """Return (doc_type, reason) or (None, exclude_reason) for a Main v3 row."""
    title = str(fields.get("Name") or fields.get("Bill Title") or "")
    bill = str(fields.get("Bill Number") or "").strip()
    chamber = str(fields.get("Chamber") or "")

    if FEDERAL_HOSTS.search(url):
        return None, "federal"
    if LEGIS_BILL.match(bill):
        return None, "legislation_bill"
    if LEGIS_URL.search(url) and not re.search(r"executive|proclamation", url, re.I):
        return None, "legislation_url"

    doc_type: str | None = None
    reasons: list[str] = []

    if re.search(r"\bexecutive\s+order\b", title, re.I):
        doc_type = "executive_order"
        reasons.append("title_eo")
    if re.search(r"executive[-_]?order|ExecutiveOrders|/eo[-/]", url, re.I):
        doc_type = doc_type or "executive_order"
        reasons.append("url_eo")
    if re.match(r"^(EO|E\.?O\.?)\b", bill, re.I) and "/proclamations/" not in url.lower():
        doc_type = "executive_order"
        reasons.append("bill_eo")

    if re.search(r"\bproclamation\b", title, re.I):
        doc_type = doc_type or "proclamation"
        reasons.append("title_proc")
    if re.search(r"proclamation|/procs|/proclamations/", url, re.I):
        doc_type = "proclamation"
        reasons.append("url_proc")
    if re.match(r"^(Proclamation|Proc\.?|Unnumbered Proclamation)\b", bill, re.I):
        doc_type = "proclamation"
        reasons.append("bill_proc")
    if re.search(r"proclaim|mmiw.*day|mmip.*day|awareness.*day", url, re.I):
        doc_type = doc_type or "proclamation"
        reasons.append("url_slug_proc")

    if doc_type:
        return doc_type, "+".join(reasons)

    if chamber.lower() == "executive" and re.search(r"governor\.|gov\.[a-z]{2}\.", url, re.I):
        if re.search(r"\.pdf$|/assets/", url, re.I):
            return "executive_order", "chamber_governor_pdf"

    return None, "other"


def load_eo_proc_audit_urls(
    client: AirtableClient,
    state_filter: str | None = None,
) -> list[_reach.AuditUrl]:
    rows: list[_reach.AuditUrl] = []
    for record in client.all_live_records():
        fields = record.get("fields") or {}
        state_raw = str(fields.get("State") or "").strip()
        state_code = state_raw[:2].upper() if len(state_raw) == 2 else state_raw.upper()
        if state_filter and state_code != state_filter.upper():
            continue
        title = str(fields.get("Bill Title") or fields.get("Name") or "")[:200]
        airtable_source = str(fields.get("Source") or "")
        for field_name, url in _reach.extract_record_urls(record):
            if LEGISCAN_RE.search(url):
                continue
            doc_type, reason = classify_eo_proc_record(fields, url)
            if not doc_type:
                continue
            rows.append(
                _reach.AuditUrl(
                    url=url,
                    normalized=normalize_url(url),
                    record_id=record["id"],
                    state=state_code,
                    title=title,
                    source_field=field_name,
                    airtable_source=airtable_source,
                    jurisdiction=state_code,
                )
            )
            rows[-1].doc_type = doc_type  # type: ignore[attr-defined]
            rows[-1].classify_reason = reason  # type: ignore[attr-defined]
    return rows


def eo_proc_sources_for_state(
    state: str,
    all_sources: list[StateSource],
    doc_type: str | None = None,
) -> list[StateSource]:
    """Enabled EO/proc sources plus proclamation announcement channels."""
    pool: list[StateSource] = []
    for src in all_sources:
        if src.state != state or src.review_needed:
            continue
        if src.content_type in EO_PROC_CONTENT_TYPES:
            if doc_type and src.content_type != doc_type:
                continue
            pool.append(src)
        elif doc_type == "proclamation" and src.content_type in PROC_CHANNEL_TYPES:
            if PROC_CHANNEL_NOTES.search(src.notes or "") or "doa" in src.source_id:
                pool.append(src)
    return pool


def matching_eo_proc_sources(
    audit_url: _reach.AuditUrl,
    all_sources: list[StateSource],
) -> tuple[list[StateSource], list[StateSource]]:
    doc_type = getattr(audit_url, "doc_type", None)
    pool = eo_proc_sources_for_state(audit_url.state, all_sources, doc_type)
    matched = [s for s in pool if _reach.host_matches_source(audit_url.url, s)]
    # Also match any source whose sample_urls contain this URL (cross-host tracking).
    norm = audit_url.normalized
    for src in pool:
        if src in matched:
            continue
        if norm in {normalize_url(u) for u in (src.sample_urls or [])}:
            matched.append(src)
    return matched, pool


def prefetch_eo_proc_crawls(
    audit_urls: list,
    all_sources: list[StateSource],
    cache: _reach.FastSourceCache,
    skip_crawl: bool,
) -> None:
    if skip_crawl:
        return
    needed: dict[str, StateSource] = {}
    for audit_url in audit_urls:
        enabled, _ = matching_eo_proc_sources(audit_url, all_sources)
        for source in enabled:
            if source.method in ("index", "rss"):
                needed[source.source_id] = source
    # Always prefetch enabled EO/proc index sources for states in the audit set.
    states = {u.state for u in audit_urls}
    for src in all_sources:
        if src.state in states and not src.review_needed and src.content_type in EO_PROC_CONTENT_TYPES:
            if src.method in ("index", "rss"):
                needed[src.source_id] = src
    for source in needed.values():
        logger.info("EO/proc crawl max_pages=%s: %s", source.max_pages, source.source_id)
        if source.method == "rss":
            cache.crawl_rss(source)
        else:
            cache.crawl_configured(source)


def build_state_coverage(
    results: list[dict],
    all_sources: list[StateSource],
) -> dict[str, dict]:
    """Per-state year coverage from Main v3 ground truth vs source config."""
    by_state: dict[str, dict] = defaultdict(
        lambda: {
            "main_v3_docs": [],
            "years_covered": [],
            "years_missing": [],
            "enabled_eo_sources": [],
            "enabled_proc_sources": [],
            "proc_channels": [],
        }
    )
    for src in all_sources:
        if src.review_needed:
            continue
        entry = by_state[src.state]
        if src.content_type == "executive_order":
            entry["enabled_eo_sources"].append(src.source_id)
        elif src.content_type == "proclamation":
            entry["enabled_proc_sources"].append(src.source_id)
        elif src.content_type in PROC_CHANNEL_TYPES and PROC_CHANNEL_NOTES.search(src.notes or ""):
            entry["proc_channels"].append(src.source_id)

    for r in results:
        st = r["state"]
        year = _extract_year(r["url"], r.get("title", ""))
        doc = {
            "url": r["url"],
            "doc_type": r.get("doc_type", ""),
            "year": year,
            "classification": r["classification"],
        }
        by_state[st]["main_v3_docs"].append(doc)
        if year and r["classification"] in ("REACHABLE", "ALREADY_TRACKED_DEDUP"):
            if year not in by_state[st]["years_covered"]:
                by_state[st]["years_covered"].append(year)
        elif year and r["classification"] not in ("ALREADY_TRACKED_DEDUP",):
            if year not in by_state[st]["years_missing"]:
                by_state[st]["years_missing"].append(year)

    for st, info in by_state.items():
        info["years_covered"] = sorted(set(info["years_covered"]))
        info["years_missing"] = sorted(set(info["years_missing"]) - set(info["years_covered"]))
    return dict(by_state)


def build_gaps(
    results: list[dict],
    all_sources: list[StateSource],
    state_coverage: dict[str, dict],
) -> list[dict]:
    gaps: list[dict] = []
    states_with_docs = {r["state"] for r in results}

    third_party = re.compile(r"azmirror\.com|medium\.com|substack", re.I)
    for r in results:
        if r["classification"] in ("REACHABLE", "ALREADY_TRACKED_DEDUP"):
            continue
        if third_party.search(r.get("url", "")):
            gaps.append(
                {
                    "state": r["state"],
                    "url": r["url"],
                    "doc_type": r.get("doc_type", ""),
                    "classification": "DUPLICATE_OPTIONAL_LINK",
                    "detail": "Third-party news duplicate; canonical gov URL already reachable",
                    "recommended_fix": "No source change needed; optional link in Main v3",
                }
            )
            continue
        fix = ""
        if r["classification"] == "TOO_DEEP":
            srcs = r.get("sources") or []
            sid = srcs[0]["source_id"] if srcs else "?"
            page = srcs[0].get("page_no") if srcs else None
            fix = f"Raise max_pages on {sid} to ≥{page}" if page else f"Raise max_pages on {sid}"
        elif r["classification"] == "ORPHAN_OR_WRONG_HOST":
            fix = "Add sample_url or year_slug_template; check cross-domain listing (e.g. NC DOA)"
        elif r["classification"] == "SOURCE_MISSING_OR_QUARANTINED":
            st = r["state"]
            has_eo = bool(state_coverage.get(st, {}).get("enabled_eo_sources"))
            has_proc = bool(state_coverage.get(st, {}).get("enabled_proc_sources"))
            if not has_eo and not has_proc:
                fix = f"Bootstrap/enable EO or proclamation source for {st}"
            else:
                fix = f"Add host {r['host']} to allowed domains or sample_urls on {st} sources"
        elif r["classification"] == "DEAD_URL":
            if "ncadmin" in r.get("url", "") or "doa.nc.gov" in r.get("url", ""):
                fix = "Stale Main v3 link (403/redirect to doa.nc.gov); NC proclamation coverage via nc-nc-governor-proclamations + nc-nc-doa-press-releases"
            else:
                fix = "Refresh or replace dead URL in Main v3"
        gaps.append(
            {
                "state": r["state"],
                "url": r["url"],
                "doc_type": r.get("doc_type", ""),
                "classification": r["classification"],
                "detail": r.get("detail", ""),
                "recommended_fix": fix,
            }
        )

    for st in sorted(states_with_docs):
        cov = state_coverage.get(st, {})
        has_eo = bool(cov.get("enabled_eo_sources"))
        has_proc = bool(cov.get("enabled_proc_sources"))
        docs = cov.get("main_v3_docs", [])
        proc_docs = [d for d in docs if d.get("doc_type") == "proclamation"]
        eo_docs = [d for d in docs if d.get("doc_type") == "executive_order"]
        eo_ok = all(
            d["classification"] in ("REACHABLE", "ALREADY_TRACKED_DEDUP") for d in eo_docs
        ) if eo_docs else True
        proc_ok = all(
            d["classification"] in ("REACHABLE", "ALREADY_TRACKED_DEDUP") for d in proc_docs
        ) if proc_docs else True
        if eo_docs and not has_eo and not eo_ok:
            gaps.append(
                {
                    "state": st,
                    "url": "",
                    "doc_type": "executive_order",
                    "classification": "NO_ENABLED_EO_SOURCE",
                    "detail": f"{st} has {len(eo_docs)} Main v3 EO(s) but no enabled EO source",
                    "recommended_fix": f"Enable or bootstrap EO source for {st}",
                }
            )
        if proc_docs and not has_proc and not cov.get("proc_channels") and not proc_ok:
            gaps.append(
                {
                    "state": st,
                    "url": "",
                    "doc_type": "proclamation",
                    "classification": "NO_ENABLED_PROC_SOURCE",
                    "detail": f"{st} has {len(proc_docs)} Main v3 proclamation(s) but no enabled source",
                    "recommended_fix": f"Enable proclamation source or governor-news channel for {st}",
                }
            )

    shallow = [
        s
        for s in all_sources
        if not s.review_needed
        and s.content_type in EO_PROC_CONTENT_TYPES
        and s.method == "index"
        and s.max_pages <= DEFAULT_MAX_PAGES
    ]
    if shallow:
        gaps.append(
            {
                "state": "",
                "url": "",
                "doc_type": "",
                "classification": "SYSTEMIC_SHALLOW_DEPTH",
                "detail": f"{len(shallow)} EO/proc sources still at default max_pages={DEFAULT_MAX_PAGES}",
                "recommended_fix": "Review: " + ", ".join(s.source_id for s in shallow[:6]),
            }
        )

    return gaps


def states_without_ground_truth(
    all_sources: list[StateSource],
    states_with_docs: set[str],
) -> list[dict]:
    by_state: dict[str, list[str]] = defaultdict(list)
    for src in all_sources:
        if src.review_needed or src.content_type not in EO_PROC_CONTENT_TYPES:
            continue
        by_state[src.state].append(f"{src.content_type}:{src.source_id}")
    out = []
    for st in sorted(by_state):
        if st not in states_with_docs:
            out.append({"state": st, "enabled_sources": by_state[st]})
    return out


def write_markdown(
    path: Path,
    payload: dict,
    state_coverage: dict,
    gaps: list[dict],
    no_ground_truth: list[dict],
) -> None:
    s = payload["summary"]
    lines = [
        "# Main v3 State EO/Proclamation Completeness Audit",
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
        f"- **Main v3 state EO/proc URLs:** {s['total_urls']}",
        f"- **By doc type:** EO={s['by_doc_type'].get('executive_order', 0)}, "
        f"Proclamation={s['by_doc_type'].get('proclamation', 0)}",
        f"- **States with ground truth:** {s['states_with_docs']}",
        f"- **States with enabled EO/proc sources (no Main v3 docs):** {len(no_ground_truth)}",
        "",
        "## Classification counts",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for cls in _reach.CLASSIFICATIONS:
        lines.append(f"| {cls} | {s['by_classification'].get(cls, 0)} |")

    lines.extend(["", "## Per-state coverage", ""])
    lines.append("| State | Main v3 | EO src | Proc src | Channels | Years OK | Years gap | Issues |")
    lines.append("|---|---:|---:|---:|---|---|---|---|")
    for st in sorted(state_coverage.keys()):
        if not state_coverage[st]["main_v3_docs"] and not (
            state_coverage[st]["enabled_eo_sources"] or state_coverage[st]["enabled_proc_sources"]
        ):
            continue
        info = state_coverage[st]
        n = len(info["main_v3_docs"])
        if n == 0:
            continue
        issues = Counter(d["classification"] for d in info["main_v3_docs"] if d["classification"] not in ("REACHABLE", "ALREADY_TRACKED_DEDUP"))
        issue_str = ", ".join(f"{k}={v}" for k, v in sorted(issues.items())) or "—"
        channels = info.get("proc_channels") or []
        lines.append(
            f"| {st} | {n} | {len(info['enabled_eo_sources'])} | "
            f"{len(info['enabled_proc_sources'])} | "
            f"{len(channels)} | "
            f"{', '.join(info['years_covered']) or '—'} | "
            f"{', '.join(info['years_missing']) or '—'} | {issue_str} |"
        )

    lines.extend(["", "## Gaps (actionable)", ""])
    for g in gaps:
        lines.append(f"- **[{g['classification']}]** {g['state'] or '—'}")
        if g.get("url"):
            lines.append(f"  - URL: {g['url']}")
        lines.append(f"  - {g['detail']}")
        lines.append(f"  - Fix: {g['recommended_fix']}")

    if no_ground_truth:
        lines.extend(["", "## No Main v3 ground truth (enabled sources only)", ""])
        lines.append(
            "These states have enabled EO/proc sources but zero matching Main v3 rows — "
            "completeness cannot be verified from Main v3 alone."
        )
        for row in no_ground_truth[:20]:
            lines.append(f"- **{row['state']}**: {', '.join(row['enabled_sources'][:3])}")
        if len(no_ground_truth) > 20:
            lines.append(f"- … and {len(no_ground_truth) - 20} more")

    if payload.get("fixes_applied"):
        lines.extend(["", "## Fixes applied this pass", ""])
        for fix in payload["fixes_applied"]:
            lines.append(f"- {fix}")

    lines.extend(["", "## Artifacts", "", f"- JSON: `{payload['json_path']}`", f"- Markdown: `{path}`"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compute_verdict(results: list[dict], gaps: list[dict]) -> str:
    # Canonical gov URLs matter; third-party duplicates (e.g. azmirror) are non-blocking.
    third_party = re.compile(r"azmirror\.com|medium\.com|substack", re.I)
    canonical = [r for r in results if not third_party.search(r.get("url", ""))]
    actionable = [
        r for r in canonical
        if r["classification"] not in ("REACHABLE", "ALREADY_TRACKED_DEDUP")
    ]
    if not canonical:
        return "**No state-level EO/proc rows in Main v3** — cannot assess completeness against ground truth."
    reachable = sum(
        1 for r in canonical if r["classification"] in ("REACHABLE", "ALREADY_TRACKED_DEDUP")
    )
    pct = round(100 * reachable / len(canonical))
    dupes = len(results) - len(canonical)
    dupe_note = f" ({dupes} third-party duplicate URL(s) excluded from verdict)" if dupes else ""
    if not actionable:
        return (
            f"**Solid.** All {len(canonical)} canonical state EO/proc Main v3 URLs are "
            f"REACHABLE or tracked via sample_urls ({pct}%){dupe_note}."
        )
    blocking = [
        r for r in actionable
        if r["classification"] in ("TOO_DEEP", "SOURCE_MISSING_OR_QUARANTINED", "ORPHAN_OR_WRONG_HOST")
    ]
    dead = [r for r in actionable if r["classification"] == "DEAD_URL"]
    if not blocking and dead:
        return (
            f"**Discovery sources solid ({pct}% reachable).** "
            f"{len(dead)} dead URL(s) in Main v3 need refresh (not a source gap){dupe_note}."
        )
    if len(blocking) <= 2 and pct >= 70:
        return (
            f"**Mostly solid ({pct}% reachable)** with {len(blocking)} source gap(s): "
            + "; ".join(f"{r['state']}={r['classification']}" for r in blocking[:4])
            + dupe_note
        )
    return (
        f"**Gaps remain ({pct}% reachable).** {len(actionable)} of {len(canonical)} "
        f"canonical URLs need fixes — see Gaps section.{dupe_note}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Main v3 EO/proclamation completeness audit")
    parser.add_argument("--state", help="Limit to one state")
    parser.add_argument("--skip-crawl", action="store_true")
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv(ROOT / ".env")
    started = time.time()

    client = AirtableClient()
    audit_urls = load_eo_proc_audit_urls(client, args.state)
    if args.limit:
        audit_urls = audit_urls[: args.limit]

    raw = json.loads(STATE_SOURCES_PATH.read_text(encoding="utf-8"))
    all_sources = load_sources_data(raw)

    http = HttpFetcher(USER_AGENT, per_domain_delay=args.delay)
    cache = _reach.FastSourceCache(http)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    logger.info("EO/proc audit: %s URL(s) across %s state(s)", len(audit_urls), len({u.state for u in audit_urls}))
    prefetch_eo_proc_crawls(audit_urls, all_sources, cache, args.skip_crawl)

    seen: set[str] = set()
    results: list[dict] = []
    for i, audit_url in enumerate(audit_urls, 1):
        alive, status = _reach.check_url_alive(audit_url.url, session)
        enabled, all_matched = matching_eo_proc_sources(audit_url, all_sources)
        # Fall back to any host-matching source if EO/proc pool empty (e.g. LA governor news).
        if not enabled and not all_matched:
            enabled, all_matched = _reach.matching_sources(audit_url, all_sources, [])
        row = _reach.classify_url(
            audit_url, enabled, all_matched, alive, cache, args.skip_crawl, seen, all_sources
        )
        row["http_status"] = status
        row["doc_type"] = getattr(audit_url, "doc_type", "")
        row["classify_reason"] = getattr(audit_url, "classify_reason", "")
        results.append(row)
        if i % 10 == 0 or i == len(audit_urls):
            logger.info("Classified %s/%s (%.0fs)", i, len(audit_urls), time.time() - started)

    state_coverage = build_state_coverage(results, all_sources)
    states_with_docs = {r["state"] for r in results}
    gaps = build_gaps(results, all_sources, state_coverage)
    no_ground_truth = states_without_ground_truth(all_sources, states_with_docs)

    by_class = Counter(r["classification"] for r in results)
    by_doc = Counter(r.get("doc_type", "") for r in results)
    summary = {
        "total_urls": len(results),
        "states_with_docs": len(states_with_docs),
        "by_classification": dict(by_class),
        "by_doc_type": dict(by_doc),
        "by_state": {
            st: len([r for r in results if r["state"] == st]) for st in sorted(states_with_docs)
        },
    }
    elapsed = round(time.time() - started, 1)
    verdict = compute_verdict(results, gaps)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    json_path = PROBE_DIR / f"main_v3_eo_proc_completeness_{ts}.json"
    md_path = PROBE_DIR / f"main_v3_eo_proc_completeness_{ts}.md"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "methodology": {
            "ground_truth": "Main v3 non-LegiScan state EO/proclamation URLs",
            "source_filter": "enabled executive_order + proclamation (+ proclamation announcement channels)",
            "crawl": "host-matched at configured max_pages only",
            "depth_detection": "targeted page probes (NC fixtures + max_pages+1 edge)",
            "airtable": "read-only",
        },
        "verdict": verdict,
        "summary": summary,
        "state_coverage": state_coverage,
        "gaps": gaps,
        "no_ground_truth_states": no_ground_truth,
        "fixes_applied": [],
        "results": results,
        "json_path": str(json_path),
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_path, payload, state_coverage, gaps, no_ground_truth)

    print(json.dumps({**summary, "verdict": verdict, "elapsed_seconds": elapsed}, indent=2))
    print(f"\nWrote {json_path}\nWrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
