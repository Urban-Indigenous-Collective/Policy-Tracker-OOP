#!/usr/bin/env python3
"""Audit and repair ungrounded gov metadata on Pending rows.

Re-fetches source text and applies check_record_consistency to clear
Last Update / Sponsors / Chamber Details / Session when they are not
grounded in the document.

Usage:
  python scripts/audit_ungrounded_metadata.py
  python scripts/audit_ungrounded_metadata.py --apply
  python scripts/audit_ungrounded_metadata.py --apply --reanalyze
  python scripts/audit_ungrounded_metadata.py --record-id recXXX --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, BILL_TEXT_FIELD, REVIEW_STATUS_REJECTED
from api_client import APIClient
from bill_processor import BillProcessor
from content_guard import check_record_consistency, merge_warnings
from document_processor import DocumentProcessor
from indigenous_database import IndigenousDatabase
from llm.factory import get_llm_provider

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_METADATA_FIELDS = (
    "Last Update",
    "Sponsors of the Legislation",
    "Chamber Details",
    "Session",
    "Bill Number",
    "Validation Warnings",
)

_UNGROUNDED_METADATA_RE = re.compile(
    r"(last update|sponsor|chamber details|session|bill number).*not grounded",
    re.IGNORECASE,
)


@dataclass
class AuditStats:
    processed: int = 0
    changed: int = 0
    unchanged: int = 0
    failed: int = 0
    cleared_last_update: int = 0
    cleared_sponsors: int = 0
    cleared_chamber: int = 0
    cleared_session: int = 0
    cleared_bill_number: int = 0
    needs_reanalyze: list[str] = field(default_factory=list)
    applied: int = 0


def _record_url(fields: dict) -> str:
    return (
        fields.get(BILL_OVERVIEW_LINK_FIELD)
        or fields.get("Bill Overview")
        or fields.get(BILL_TEXT_FIELD)
        or ""
    )


def _targets_match(fields: dict) -> bool:
    warnings = str(fields.get("Validation Warnings") or "").lower()
    if "last update" in warnings and "not grounded" in warnings:
        return True
    if "chamber details" in warnings and "not grounded" in warnings:
        return True
    if "session" in warnings and "not grounded" in warnings:
        return True
    if "sponsor" in warnings and "not grounded" in warnings:
        return True
    if "bill number" in warnings and "not grounded" in warnings:
        return True
    return fields.get("Source") == "Federal Site"


def _build_bill_data(fields: dict) -> dict:
    return {
        "Name": fields.get("Name", ""),
        "Bill Number": fields.get("Bill Number", ""),
        "Last Update": fields.get("Last Update", ""),
        "Sponsors of the Legislation": fields.get("Sponsors of the Legislation", ""),
        "Chamber Details": fields.get("Chamber Details", ""),
        "Session": fields.get("Session", ""),
        "Bill Text": _record_url(fields),
        "Source": fields.get("Source", ""),
        "Validation Warnings": fields.get("Validation Warnings", ""),
    }


def _strip_ungrounded_metadata_warnings(existing: str) -> str:
    parts = [p.strip() for p in str(existing or "").split(";") if p.strip()]
    kept = [
        p
        for p in parts
        if p.lower() != "cleared" and not _UNGROUNDED_METADATA_RE.search(p)
    ]
    return "; ".join(kept)


def _revised_warnings(fields: dict, consistency_warnings: list[str]) -> str:
    """Drop stale ungrounded-metadata warnings after fields are cleared."""
    del consistency_warnings  # audit trail lives in logs, not Validation Warnings
    return _strip_ungrounded_metadata_warnings(fields.get("Validation Warnings", ""))


def _needs_reanalyze(
    fields: dict,
    updates: dict,
    consistency_warnings: list[str],
) -> bool:
    revised = _revised_warnings(fields, consistency_warnings)
    if _UNGROUNDED_METADATA_RE.search(revised):
        return True
    if fields.get("Source") == "Federal Site" and updates.get("Last Update") in ("", None):
        return True
    cleared_count = sum(
        1
        for key in ("Last Update", "Sponsors of the Legislation", "Chamber Details", "Session")
        if key in updates and updates.get(key) in ("", None)
    )
    return cleared_count >= 2


def _count_clears(stats: AuditStats, fields: dict, updates: dict) -> None:
    if "Last Update" in updates and updates["Last Update"] != fields.get("Last Update"):
        if not str(updates.get("Last Update") or "").strip():
            stats.cleared_last_update += 1
    if "Sponsors of the Legislation" in updates and updates["Sponsors of the Legislation"] != fields.get(
        "Sponsors of the Legislation"
    ):
        if not str(updates.get("Sponsors of the Legislation") or "").strip():
            stats.cleared_sponsors += 1
    if "Chamber Details" in updates and updates["Chamber Details"] != fields.get("Chamber Details"):
        if not str(updates.get("Chamber Details") or "").strip():
            stats.cleared_chamber += 1
    if "Session" in updates and updates["Session"] != fields.get("Session"):
        if not str(updates.get("Session") or "").strip():
            stats.cleared_session += 1
    if "Bill Number" in updates and updates["Bill Number"] != fields.get("Bill Number"):
        if not str(updates.get("Bill Number") or "").strip():
            stats.cleared_bill_number += 1


def audit_record(
    processor: BillProcessor, fields: dict, *, refresh: bool = False
) -> tuple[dict | None, list[str], str]:
    url = _record_url(fields)
    if not url:
        return None, [], "no_url"

    processor.compiled_bill = {}
    ok, msg = processor.get_doc_text(url, refresh=refresh)
    if not ok:
        return None, [], f"fetch_failed:{msg}"

    source_text = processor.compiled_bill.get("decoded_text") or ""
    if not source_text or str(source_text).startswith("Error"):
        return None, [], "empty_source"

    bill_data = _build_bill_data(fields)
    consistency = check_record_consistency(bill_data, source_text)
    if not consistency.ok:
        return None, [], f"blocked:{consistency.blocking_code}"

    updates: dict = {}
    for key in _METADATA_FIELDS:
        if key == "Validation Warnings":
            continue
        if bill_data.get(key) != fields.get(key):
            updates[key] = bill_data.get(key, "")

    revised = _revised_warnings(fields, consistency.warnings)
    if revised != str(fields.get("Validation Warnings") or "").strip():
        updates["Validation Warnings"] = revised

    return updates, consistency.warnings, "ok"


def reanalyze_record(
    processor: BillProcessor, fields: dict, *, refresh: bool = False
) -> tuple[dict | None, list[str], str]:
    from scripts.reanalyze_pending_warnings import _ANALYSIS_UPDATE_FIELDS, _prepare_updates

    url = _record_url(fields)
    if not url:
        return None, [], "no_url"

    processor.compiled_bill = {}
    ok, msg = processor.process_bill(url, refresh=refresh)
    if not ok:
        return None, [], f"process_failed:{msg}"

    bill_data = processor.compiled_bill.get("bill_data") or {}
    if not bill_data:
        return None, [], "no_bill_data"

    source_text = processor.compiled_bill.get("decoded_text") or ""
    bill_data = dict(bill_data)
    bill_data["Source"] = fields.get("Source", bill_data.get("Source", ""))
    consistency = check_record_consistency(bill_data, source_text)
    if consistency.warnings:
        existing = str(bill_data.get("Validation Warnings") or "").strip()
        bill_data["Validation Warnings"] = merge_warnings(existing, consistency.warnings)
    elif "Validation Warnings" in bill_data:
        bill_data["Validation Warnings"] = _strip_ungrounded_metadata_warnings(
            bill_data.get("Validation Warnings", "")
        )

    updates = {k: bill_data[k] for k in _ANALYSIS_UPDATE_FIELDS if k in bill_data}
    return _prepare_updates(updates, fields), consistency.warnings, "ok"


def _print_summary(stats: AuditStats, apply: bool, reanalyze: bool) -> None:
    print(
        f"processed={stats.processed} changed={stats.changed} unchanged={stats.unchanged} "
        f"failed={stats.failed} applied={stats.applied} reanalyze={reanalyze}"
    )
    print(
        f"cleared_last_update={stats.cleared_last_update} cleared_sponsors={stats.cleared_sponsors} "
        f"cleared_chamber={stats.cleared_chamber} cleared_session={stats.cleared_session} "
        f"cleared_bill_number={stats.cleared_bill_number}"
    )
    if stats.needs_reanalyze:
        print(f"needs_reanalyze={len(stats.needs_reanalyze)}")
        for rid in stats.needs_reanalyze:
            print(f"  {rid}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reanalyze", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--record-id", action="append", default=[])
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
        if not args.record_id and not _targets_match(fields):
            continue
        targets.append(record)

    if args.limit:
        targets = targets[: args.limit]

    stats = AuditStats(processed=len(targets))

    for i, record in enumerate(targets, 1):
        rid = record["id"]
        fields = record.get("fields") or {}
        name = str(fields.get("Name") or "")[:70]
        try:
            if args.reanalyze:
                updates, consistency_warnings, status = reanalyze_record(
                    processor, fields, refresh=args.refresh
                )
            else:
                updates, consistency_warnings, status = audit_record(
                    processor, fields, refresh=args.refresh
                )
        except Exception as exc:
            logger.exception("Audit failed for %s: %s", rid, exc)
            stats.failed += 1
            continue

        if updates is None:
            logger.warning("[%d/%d] %s skipped: %s", i, len(targets), rid, status)
            stats.failed += 1
            continue

        delta = {
            k: (fields.get(k), updates.get(k))
            for k in updates
            if updates.get(k) != fields.get(k)
        }
        if not delta:
            stats.unchanged += 1
            logger.info("[%d/%d] %s unchanged", i, len(targets), rid)
            if not args.reanalyze and _needs_reanalyze(fields, {}, consistency_warnings):
                stats.needs_reanalyze.append(rid)
            continue

        stats.changed += 1
        _count_clears(stats, fields, updates)
        logger.info("[%d/%d] %s %s", i, len(targets), rid, name)
        for key, (old, new) in delta.items():
            logger.info("  %s: %r -> %r", key, old, new)

        if not args.reanalyze and _needs_reanalyze(fields, updates, consistency_warnings):
            stats.needs_reanalyze.append(rid)

        if args.apply:
            client.update_record(client.pending_table, rid, updates)
            stats.applied += 1

        processor.compiled_bill = {}
        time.sleep(0.3)

    _print_summary(stats, args.apply, args.reanalyze)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
