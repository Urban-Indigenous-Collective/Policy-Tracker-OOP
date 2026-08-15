#!/usr/bin/env python3
"""Full LLM re-analysis for Pending rows that still have Validation Warnings.

Re-runs BillProcessor.process_bill (fetch + metadata + LLM analysis) and
updates analysis fields on the Pending record.

Usage:
  python scripts/reanalyze_pending_warnings.py           # dry-run
  python scripts/reanalyze_pending_warnings.py --apply   # write to Airtable
  python scripts/reanalyze_pending_warnings.py --apply --limit 20
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_coercion import coerce_bill_fields, coerce_categories, parse_category_tokens
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, BILL_TEXT_FIELD, REVIEW_STATUS_REJECTED
from analysis_validator import validate_categories
from api_client import APIClient
from bill_processor import BillProcessor
from content_guard import check_record_consistency
from document_processor import DocumentProcessor
from indigenous_database import IndigenousDatabase
from llm.factory import get_llm_provider

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Fields written by parse_bill_object; preserve review/discovery metadata elsewhere.
_ANALYSIS_UPDATE_FIELDS = (
    "State",
    "Name",
    "Bill Number",
    "Status",
    "Progression",
    "Chamber",
    "Chamber Details",
    "Bill Overview (Link)",
    "Bill Text",
    "Summary",
    "UIC Pros",
    "UIC Cons",
    "Mechanisms for Evaluation?",
    "Mechanisms for Evaluation",
    "Gender Inclusive Language?",
    "Gender Inclusive Language",
    "Prevention Efforts?",
    "Prevention Efforts",
    "Level of Survivor / Relative Input?",
    "Level of Survivor / Relative Input",
    "Centering of Indigenous Voices?",
    "Centering of Indigenous Voices",
    "Sponsors of the Legislation",
    "Indigenous Sponsorship",
    "Session",
    "Categories",
    "Last Update",
    "Validation Warnings",
)


def _strip_invalid_category_warnings(warnings: str) -> str:
    parts = [p.strip() for p in str(warnings or "").split(";") if p.strip()]
    kept = [p for p in parts if not p.startswith("Invalid category:")]
    return "; ".join(kept)


def _prepare_updates(updates: dict, existing_fields: dict) -> dict:
    """Coerce analysis fields; keep existing Categories when LLM output is bad."""
    coerced = coerce_bill_fields(updates)
    prepared = {k: coerced[k] for k in updates if k in coerced}

    if "Categories" not in updates:
        return prepared

    raw_cats = parse_category_tokens(updates.get("Categories"))
    new_cats = prepared.get("Categories") or []
    existing_cats = coerce_categories(existing_fields.get("Categories"))
    categories_preserved = False

    if validate_categories(raw_cats) or (raw_cats and not new_cats):
        if existing_cats:
            prepared["Categories"] = existing_cats
            categories_preserved = True
        else:
            prepared.pop("Categories", None)
    elif not new_cats and existing_cats:
        prepared["Categories"] = existing_cats
        categories_preserved = True

    final_cats = prepared.get("Categories") or []
    if final_cats and not validate_categories(final_cats):
        if "Validation Warnings" in prepared:
            prepared["Validation Warnings"] = _strip_invalid_category_warnings(
                prepared["Validation Warnings"]
            )
    elif categories_preserved and "Validation Warnings" in prepared:
        prepared["Validation Warnings"] = _strip_invalid_category_warnings(
            prepared["Validation Warnings"]
        )

    return prepared


def _record_url(fields: dict) -> str:
    return (
        fields.get(BILL_OVERVIEW_LINK_FIELD)
        or fields.get("Bill Overview")
        or fields.get(BILL_TEXT_FIELD)
        or ""
    )


def reanalyze_record(
    processor: BillProcessor, fields: dict, *, refresh: bool = False
) -> tuple[dict | None, str]:
    url = _record_url(fields)
    if not url:
        return None, "no_url"

    processor.compiled_bill = {}
    ok, msg = processor.process_bill(url, refresh=refresh)
    if not ok:
        return None, f"process_failed:{msg}"

    bill_data = processor.compiled_bill.get("bill_data") or {}
    if not bill_data:
        return None, "no_bill_data"

    source_text = processor.compiled_bill.get("decoded_text") or ""
    bill_data = dict(bill_data)
    bill_data["Source"] = fields.get("Source", bill_data.get("Source", ""))
    consistency = check_record_consistency(bill_data, source_text)
    if consistency.warnings:
        existing = str(bill_data.get("Validation Warnings") or "").strip()
        extra = "; ".join(consistency.warnings)
        bill_data["Validation Warnings"] = "; ".join(filter(None, [existing, extra]))

    updates = {k: bill_data[k] for k in _ANALYSIS_UPDATE_FIELDS if k in bill_data}
    return updates, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
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
        warnings = str(fields.get("Validation Warnings") or "").strip()
        if not warnings and not args.record_id:
            continue
        targets.append(record)

    if args.limit:
        targets = targets[: args.limit]

    cleared = 0
    reduced = 0
    failed = 0
    unchanged = 0

    for i, record in enumerate(targets, 1):
        rid = record["id"]
        fields = record.get("fields") or {}
        old = str(fields.get("Validation Warnings") or "").strip()
        try:
            updates, status = reanalyze_record(processor, fields, refresh=args.refresh)
        except Exception as exc:
            logger.exception("Reanalyze failed for %s: %s", rid, exc)
            failed += 1
            continue

        if updates is None:
            logger.warning("%s skipped: %s", rid, status)
            failed += 1
            continue

        new = str(updates.get("Validation Warnings") or "").strip()
        if new == old:
            unchanged += 1
        elif not new:
            cleared += 1
        else:
            reduced += 1

        logger.info(
            "[%d/%d] %s reanalyze warnings: %d -> %d chars",
            i,
            len(targets),
            rid,
            len(old),
            len(new),
        )

        if args.apply:
            prepared = _prepare_updates(updates, fields)
            client.update_record(client.pending_table, rid, prepared)

        processor.compiled_bill = {}
        time.sleep(0.5)

    print(
        f"processed={len(targets)} cleared={cleared} reduced={reduced} "
        f"unchanged={unchanged} failed={failed} apply={args.apply}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
