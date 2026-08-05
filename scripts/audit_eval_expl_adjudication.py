#!/usr/bin/env python3
"""Read-only audit of mechanisms/prevention eval↔expl contradictions in Pending.

Fetches source text, runs adjudication logic, and reports counts per action branch.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import REVIEW_STATUS_REJECTED
from analysis_schema import BillAnalysis, EvalAnswer
from api_client import APIClient
from bill_processor import BillProcessor
from document_processor import DocumentProcessor
from eval_expl_adjudication import AdjudicationAction, adjudicate_eval_expl
from indigenous_database import IndigenousDatabase
from llm.factory import get_llm_provider
from scripts.refresh_pending_validation_warnings import (
    _analysis_from_fields,
    _record_url,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "data" / "backups"


def _has_eval_expl_mismatch(fields: dict) -> bool:
    warnings = str(fields.get("Validation Warnings") or "")
    return (
        "mechanisms_expl provided but mechanisms_eval is not Yes" in warnings
        or "prevention_efforts_expl provided but prevention_efforts_eval is not Yes"
        in warnings
    )


def _field_action_label(adj) -> str:
    if adj is None:
        return "none"
    return adj.action.value


def audit_record(processor: BillProcessor, record: dict, *, refresh: bool = False) -> dict | None:
    fields = record.get("fields") or {}
    if not _has_eval_expl_mismatch(fields):
        return None

    url = _record_url(fields)
    rid = record["id"]
    if not url:
        return {
            "record_id": rid,
            "name": str(fields.get("Name") or "")[:80],
            "status": "no_url",
        }

    ok, msg = processor.get_doc_text(url, refresh=refresh)
    if not ok:
        return {
            "record_id": rid,
            "name": str(fields.get("Name") or "")[:80],
            "status": f"fetch_failed:{msg}",
        }

    source_text = processor.compiled_bill.get("decoded_text") or ""
    if not source_text or str(source_text).startswith("Error"):
        return {
            "record_id": rid,
            "name": str(fields.get("Name") or "")[:80],
            "status": "empty_source",
        }

    analysis_data = _analysis_from_fields(fields)
    try:
        analysis = BillAnalysis.model_validate(analysis_data)
    except Exception as exc:
        return {
            "record_id": rid,
            "name": str(fields.get("Name") or "")[:80],
            "status": f"schema_invalid:{exc}",
        }

    adj = adjudicate_eval_expl(
        analysis,
        source_text,
        name=str(fields.get("Name") or ""),
        url=url,
    )

    mech_action = _field_action_label(adj.mech)
    prev_action = _field_action_label(adj.prev)

    entry = {
        "record_id": rid,
        "name": str(fields.get("Name") or "")[:80],
        "state": str(fields.get("State") or ""),
        "source": str(fields.get("Source") or ""),
        "document_type": adj.document_type,
        "status": "ok",
        "mech_action": mech_action,
        "prev_action": prev_action,
        "mech_reason": adj.mech.reason if adj.mech else "",
        "prev_reason": adj.prev.reason if adj.prev else "",
        "mechanisms_eval": str(fields.get("Mechanisms for Evaluation?") or ""),
        "prevention_eval": str(fields.get("Prevention Efforts?") or ""),
    }
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--record-id", action="append", default=[])
    parser.add_argument(
        "--output",
        default="",
        help="Write JSON audit report here (default: data/backups/eval_expl_audit-<stamp>.json)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Bypass document text cache and re-fetch source URLs",
    )
    args = parser.parse_args()

    api = APIClient(os.environ["LEGISCAN_KEY"])
    processor = BillProcessor(
        api,
        get_llm_provider(),
        DocumentProcessor(get_llm_provider()),
        IndigenousDatabase(),
    )
    client = AirtableClient()

    targets: list[dict] = []
    for record in client.pending_table.all():
        fields = record.get("fields") or {}
        if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
            continue
        if args.record_id and record["id"] not in args.record_id:
            continue
        if not _has_eval_expl_mismatch(fields):
            continue
        targets.append(record)

    if args.limit:
        targets = targets[: args.limit]

    results: list[dict] = []
    failed = 0
    for i, record in enumerate(targets, 1):
        rid = record["id"]
        logger.info("[%d/%d] Auditing %s", i, len(targets), rid)
        try:
            entry = audit_record(processor, record, refresh=args.refresh)
        except Exception as exc:
            logger.exception("Audit failed for %s: %s", rid, exc)
            failed += 1
            entry = {"record_id": rid, "status": f"error:{exc}"}
        if entry:
            results.append(entry)
        processor.compiled_bill = {}
        time.sleep(0.3)

    mech_actions = Counter(r.get("mech_action", "none") for r in results if r.get("status") == "ok")
    prev_actions = Counter(r.get("prev_action", "none") for r in results if r.get("status") == "ok")
    doc_types = Counter(r.get("document_type", "unknown") for r in results if r.get("status") == "ok")
    statuses = Counter(r.get("status", "unknown") for r in results)

    # Combined action counts (any field needing fix)
    all_actions = Counter()
    review_records: list[dict] = []
    for r in results:
        if r.get("status") != "ok":
            continue
        for key in ("mech_action", "prev_action"):
            action = r.get(key, "none")
            if action != "none":
                all_actions[action] += 1
        if r.get("mech_action") == "review" or r.get("prev_action") == "review":
            review_records.append(r)

    report = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "target_count": len(targets),
        "result_count": len(results),
        "failed": failed,
        "status_counts": dict(statuses),
        "mech_action_counts": dict(mech_actions),
        "prev_action_counts": dict(prev_actions),
        "combined_action_counts": dict(all_actions),
        "document_type_counts": dict(doc_types),
        "review_records": review_records,
        "records": results,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = Path(args.output) if args.output else DEFAULT_OUTPUT / f"eval_expl_audit-{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"targets={len(targets)} ok={statuses.get('ok', 0)} failed={failed}")
    print(f"mech_actions={dict(mech_actions)}")
    print(f"prev_actions={dict(prev_actions)}")
    print(f"combined_actions={dict(all_actions)}")
    print(f"doc_types={dict(doc_types)}")
    print(f"review_count={len(review_records)}")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
