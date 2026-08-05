#!/usr/bin/env python3
"""Dry-run hallucination critic for Pending analysis soft fields.

Scores high-risk Pending rows (Validation Warnings or non-LegiScan source)
plus a clean LegiScan control sample. Report-only — no Airtable writes.

Usage:
  python scripts/audit_pending_hallucinations.py
  python scripts/audit_pending_hallucinations.py --limit 40 --control-sample 10
  python scripts/audit_pending_hallucinations.py --record-id recXXX
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, BILL_TEXT_FIELD, REVIEW_STATUS_REJECTED
from api_client import APIClient
from bill_processor import BillProcessor
from document_processor import DocumentProcessor
from indigenous_database import IndigenousDatabase
from llm.factory import get_llm_provider
from pending_hallucination_critic import (
    DEFAULT_EXCERPT_CHARS,
    FieldVerdict,
    run_critic,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def _record_url(fields: dict) -> str:
    return (
        fields.get(BILL_OVERVIEW_LINK_FIELD)
        or fields.get("Bill Overview")
        or fields.get(BILL_TEXT_FIELD)
        or ""
    )


def _is_high_risk(fields: dict) -> bool:
    warnings = str(fields.get("Validation Warnings") or "").strip()
    source = str(fields.get("Source") or "")
    return bool(warnings) or source != "LegiScan"


def _is_control_candidate(fields: dict) -> bool:
    warnings = str(fields.get("Validation Warnings") or "").strip()
    source = str(fields.get("Source") or "")
    return not warnings and source == "LegiScan"


def select_records(
    records: list[dict],
    *,
    limit: int,
    control_sample: int,
    source_filter: str,
    record_ids: list[str],
) -> list[tuple[dict, str]]:
    """Return (record, cohort) pairs: high_risk or control."""
    eligible: list[dict] = []
    for record in records:
        fields = record.get("fields") or {}
        if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
            continue
        if record_ids and record["id"] not in record_ids:
            continue
        if source_filter and str(fields.get("Source") or "") != source_filter:
            continue
        if not _record_url(fields):
            continue
        eligible.append(record)

    if record_ids:
        return [(r, "high_risk" if _is_high_risk(r.get("fields") or {}) else "control") for r in eligible]

    high_risk = [r for r in eligible if _is_high_risk(r.get("fields") or {})]
    controls = [r for r in eligible if _is_control_candidate(r.get("fields") or {})]

    selected: list[tuple[dict, str]] = []
    if limit:
        selected.extend((r, "high_risk") for r in high_risk[:limit])
    else:
        selected.extend((r, "high_risk") for r in high_risk)

    if control_sample and controls:
        rng = random.Random(42)
        picked = rng.sample(controls, min(control_sample, len(controls)))
        selected.extend((r, "control") for r in picked)

    return selected


def audit_record(
    record: dict,
    cohort: str,
    processor: BillProcessor,
    llm,
    *,
    excerpt_chars: int,
) -> dict:
    rid = record["id"]
    fields = record.get("fields") or {}
    url = _record_url(fields)

    ok, msg = processor.get_doc_text(url)
    if not ok:
        return {
            "record_id": rid,
            "cohort": cohort,
            "name": str(fields.get("Name") or ""),
            "state": str(fields.get("State") or ""),
            "source": str(fields.get("Source") or ""),
            "url": url,
            "validation_warnings": str(fields.get("Validation Warnings") or ""),
            "status": "fetch_failed",
            "error": msg,
        }

    source_text = processor.compiled_bill.get("decoded_text") or ""
    if not source_text or str(source_text).startswith("Error"):
        return {
            "record_id": rid,
            "cohort": cohort,
            "name": str(fields.get("Name") or ""),
            "state": str(fields.get("State") or ""),
            "source": str(fields.get("Source") or ""),
            "url": url,
            "validation_warnings": str(fields.get("Validation Warnings") or ""),
            "status": "empty_source",
            "source_len": len(source_text or ""),
        }

    result, warnings = run_critic(llm, fields, source_text, excerpt_chars=excerpt_chars)
    if result is None:
        return {
            "record_id": rid,
            "cohort": cohort,
            "name": str(fields.get("Name") or ""),
            "state": str(fields.get("State") or ""),
            "source": str(fields.get("Source") or ""),
            "url": url,
            "validation_warnings": str(fields.get("Validation Warnings") or ""),
            "status": "critic_failed",
            "error": "; ".join(warnings),
            "source_len": len(source_text),
        }

    return {
        "record_id": rid,
        "cohort": cohort,
        "name": str(fields.get("Name") or ""),
        "state": str(fields.get("State") or ""),
        "source": str(fields.get("Source") or ""),
        "url": url,
        "validation_warnings": str(fields.get("Validation Warnings") or ""),
        "status": "ok",
        "source_len": len(source_text),
        "is_grounded": result.is_grounded,
        "confidence": result.confidence,
        "overall_rationale": result.overall_rationale,
        "issues": [issue.model_dump(mode="json") for issue in result.issues],
        "field_verdicts": {k: v.value for k, v in result.field_verdicts.items()},
        "suspect_or_bad_fields": result.suspect_or_bad_fields,
        "critic_warnings": warnings,
    }


def _summarize(rows: list[dict]) -> dict:
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    by_cohort: dict[str, list[dict]] = {}
    for row in ok_rows:
        by_cohort.setdefault(row["cohort"], []).append(row)

    cohort_stats = {}
    for cohort, items in by_cohort.items():
        grounded = sum(1 for r in items if r.get("is_grounded"))
        with_issues = sum(1 for r in items if r.get("issues"))
        suspect = sum(1 for r in items if r.get("suspect_or_bad_fields"))
        cohort_stats[cohort] = {
            "count": len(items),
            "grounded": grounded,
            "grounded_rate": round(grounded / len(items), 3) if items else 0.0,
            "with_issues": with_issues,
            "with_suspect_fields": suspect,
        }

    severities = Counter(
        issue.get("severity")
        for row in ok_rows
        for issue in row.get("issues") or []
    )
    fields = Counter(
        issue.get("field")
        for row in ok_rows
        for issue in row.get("issues") or []
    )
    verdicts = Counter(
        verdict
        for row in ok_rows
        for verdict in (row.get("field_verdicts") or {}).values()
        if verdict != FieldVerdict.OK.value
    )

    return {
        "total_selected": len(rows),
        "fetch_failed": sum(1 for r in rows if r.get("status") == "fetch_failed"),
        "empty_source": sum(1 for r in rows if r.get("status") == "empty_source"),
        "critic_failed": sum(1 for r in rows if r.get("status") == "critic_failed"),
        "audited_ok": len(ok_rows),
        "cohort_stats": cohort_stats,
        "issue_severities": dict(severities),
        "issue_fields": dict(fields.most_common(10)),
        "non_ok_verdicts": dict(verdicts),
    }


def _render_markdown(summary: dict, rows: list[dict], ts: str) -> str:
    lines = [
        f"# Pending hallucination critic dry-run ({ts})",
        "",
        "## Summary",
        "",
        f"- Selected: {summary['total_selected']}",
        f"- Audited OK: {summary['audited_ok']}",
        f"- Fetch failed: {summary['fetch_failed']}",
        f"- Empty source: {summary['empty_source']}",
        f"- Critic failed: {summary['critic_failed']}",
        "",
        "## Cohort stats",
        "",
    ]
    for cohort, stats in summary.get("cohort_stats", {}).items():
        lines.append(
            f"- **{cohort}**: n={stats['count']} grounded={stats['grounded']} "
            f"({stats['grounded_rate']:.0%}) with_issues={stats['with_issues']} "
            f"suspect_fields={stats['with_suspect_fields']}"
        )

    lines.extend(["", "## Top issue severities", ""])
    for sev, count in summary.get("issue_severities", {}).items():
        lines.append(f"- {sev}: {count}")

    lines.extend(["", "## Top flagged fields", ""])
    for field, count in summary.get("issue_fields", {}).items():
        lines.append(f"- {field}: {count}")

    flagged = [
        r for r in rows
        if r.get("status") == "ok" and (r.get("issues") or r.get("suspect_or_bad_fields"))
    ]
    lines.extend(["", "## Flagged records (sample)", ""])
    for row in flagged[:15]:
        issues = row.get("issues") or []
        issue_preview = "; ".join(
            f"{i.get('field')}:{i.get('severity')}" for i in issues[:3]
        )
        lines.append(
            f"- `{row['record_id']}` [{row['cohort']}] {row['state']} "
            f"{row['name'][:60]!r} grounded={row.get('is_grounded')} "
            f"issues={len(issues)} {issue_preview}"
        )
        if row.get("overall_rationale"):
            lines.append(f"  - {row['overall_rationale'][:200]}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40, help="Max high-risk rows to audit")
    parser.add_argument(
        "--control-sample",
        type=int,
        default=10,
        help="Clean LegiScan control rows (no Validation Warnings)",
    )
    parser.add_argument("--source", default="", help="Filter by Source field")
    parser.add_argument("--record-id", action="append", default=[], dest="record_ids")
    parser.add_argument(
        "--excerpt-chars",
        type=int,
        default=DEFAULT_EXCERPT_CHARS,
        help="Source text chars sent to critic",
    )
    parser.add_argument("--sleep", type=float, default=0.5, help="Pause between LLM calls")
    args = parser.parse_args()

    client = AirtableClient()
    llm = get_llm_provider()
    processor = BillProcessor(
        APIClient(os.environ["LEGISCAN_KEY"]),
        llm,
        DocumentProcessor(llm),
        IndigenousDatabase(),
    )

    if args.record_ids:
        records = [client.pending_table.get(rid) for rid in args.record_ids]
    else:
        records = client.pending_table.all()

    selected = select_records(
        records,
        limit=args.limit,
        control_sample=args.control_sample,
        source_filter=args.source,
        record_ids=args.record_ids,
    )

    logger.info(
        "Selected %d records (%d high_risk, %d control)",
        len(selected),
        sum(1 for _, c in selected if c == "high_risk"),
        sum(1 for _, c in selected if c == "control"),
    )

    rows: list[dict] = []
    for idx, (record, cohort) in enumerate(selected, start=1):
        logger.info(
            "[%d/%d] %s (%s)",
            idx,
            len(selected),
            record["id"],
            cohort,
        )
        row = audit_record(
            record,
            cohort,
            processor,
            llm,
            excerpt_chars=args.excerpt_chars,
        )
        rows.append(row)
        if args.sleep and idx < len(selected):
            time.sleep(args.sleep)

    summary = _summarize(rows)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"generated_at": ts, "summary": summary, "records": rows}

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / f"pending_hallucination_audit_{ts}.json"
    md_path = REPORTS_DIR / f"pending_hallucination_audit_{ts}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(summary, rows, ts), encoding="utf-8")

    print(f"selected={summary['total_selected']} audited_ok={summary['audited_ok']}")
    for cohort, stats in summary.get("cohort_stats", {}).items():
        print(
            f"  {cohort}: n={stats['count']} grounded_rate={stats['grounded_rate']:.0%} "
            f"with_issues={stats['with_issues']}"
        )
    print(f"reports: {json_path}")
    print(f"reports: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
