#!/usr/bin/env python3
"""Re-validate Pending rows with Validation Warnings using current quote repair logic.

Does not re-run LLM analysis — re-fetches source text and re-applies validators.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_coercion import coerce_categories, parse_category_tokens
from analysis_validator import validate_categories
from analysis_schema import BillAnalysis, EvalAnswer, ProsConsResult
from analysis_validator import (
    analysis_to_compiled_fields,
    validate_bill_analysis,
    validate_pros_cons,
)
from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, BILL_TEXT_FIELD, REVIEW_STATUS_REJECTED
from bill_processor import BillProcessor
from content_guard import check_record_consistency
from document_processor import DocumentProcessor
from indigenous_database import IndigenousDatabase
from llm.factory import get_llm_provider
from api_client import APIClient

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_NUMBERED_LINE = re.compile(r"^\d+\.\s*(.*)$")


def _parse_numbered_list(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw or raw.lower() in {"no", "n/a"}:
        return []
    items: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _NUMBERED_LINE.match(line)
        items.append(match.group(1).strip() if match else line)
    return items


def _eval_from_field(value: str) -> str:
    """Return Airtable-style eval strings for BillAnalysis.model_validate().

    Do not pass EvalAnswer enum objects — normalize_eval uses str(value), and
    str(EvalAnswer.YES) is "EvalAnswer.YES", which coerces to No.
    """
    text = str(value or "").strip().lower()
    if text == "yes":
        return EvalAnswer.YES.value
    if text == "somewhat":
        return EvalAnswer.SOMEWHAT.value
    return EvalAnswer.NO.value


def _analysis_from_fields(fields: dict) -> dict:
    categories = coerce_categories(fields.get("Categories"))
    return {
        "summary": str(fields.get("Summary") or "Pending record summary."),
        "gender_inclusive_eval": _eval_from_field(fields.get("Gender Inclusive Language?")),
        "gender_inclusive_expl": str(fields.get("Gender Inclusive Language") or ""),
        "mechanisms_eval": _eval_from_field(fields.get("Mechanisms for Evaluation?")),
        "mechanisms_expl": _parse_numbered_list(fields.get("Mechanisms for Evaluation")),
        "prevention_efforts_eval": _eval_from_field(fields.get("Prevention Efforts?")),
        "prevention_efforts_expl": _parse_numbered_list(fields.get("Prevention Efforts")),
        "centering_indigenous_voices_eval": _eval_from_field(
            fields.get("Centering of Indigenous Voices?")
        ),
        "centering_indigenous_voices_expl": str(fields.get("Centering of Indigenous Voices") or ""),
        "survivor_relative_input_eval": _eval_from_field(
            fields.get("Level of Survivor / Relative Input?")
        ),
        "survivor_relative_input_expl": str(fields.get("Level of Survivor / Relative Input") or ""),
        "categories": categories or ["Taskforce"],
    }


def _pros_cons_from_fields(fields: dict) -> dict:
    return {
        "uic_pros": _parse_numbered_list(fields.get("UIC Pros")),
        "uic_cons": _parse_numbered_list(fields.get("UIC Cons")),
    }


def _record_url(fields: dict) -> str:
    return (
        fields.get(BILL_OVERVIEW_LINK_FIELD)
        or fields.get("Bill Overview")
        or fields.get(BILL_TEXT_FIELD)
        or ""
    )


def _strip_invalid_category_warnings(warnings: str) -> str:
    parts = [p.strip() for p in str(warnings or "").split(";") if p.strip()]
    kept = [p for p in parts if not p.startswith("Invalid category:")]
    return "; ".join(kept)


def _strip_eval_expl_fix_warnings(warnings: str) -> str:
    """Drop stale eval_expl_fix audit-trail entries from Validation Warnings."""
    parts = [p.strip() for p in str(warnings or "").split(";") if p.strip()]
    kept = [p for p in parts if not p.startswith("eval_expl_fix:")]
    return "; ".join(kept)


def _prepare_updates(updates: dict, existing_fields: dict) -> dict:
    """Coerce Categories before write; preserve existing when output is bad."""
    prepared = dict(updates)
    if "Categories" not in prepared:
        return prepared

    raw_cats = parse_category_tokens(prepared.get("Categories"))
    new_cats = coerce_categories(prepared.get("Categories"))
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
    else:
        prepared["Categories"] = new_cats

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


def _airtable_updates_from_compiled(compiled: dict) -> dict:
    return {
        "Summary": compiled.get("chat_summary", ""),
        "Gender Inclusive Language?": compiled.get("gender_inclusive_eval", ""),
        "Gender Inclusive Language": compiled.get("gender_inclusive_expl", ""),
        "Mechanisms for Evaluation?": compiled.get("mechanisms_eval", ""),
        "Mechanisms for Evaluation": compiled.get("mechanisms_expl", ""),
        "Prevention Efforts?": compiled.get("prevention_efforts_eval", ""),
        "Prevention Efforts": compiled.get("prevention_efforts_expl", ""),
        "Centering of Indigenous Voices?": compiled.get("centering_indigenous_voices_eval", ""),
        "Centering of Indigenous Voices": compiled.get("centering_indigenous_voices_expl", ""),
        "Level of Survivor / Relative Input?": compiled.get("survivor_relative_input_eval", ""),
        "Level of Survivor / Relative Input": compiled.get("survivor_relative_input_expl", ""),
        "Categories": compiled.get("categories_eval", ""),
        "UIC Pros": compiled.get("uic_pros", ""),
        "UIC Cons": compiled.get("uic_cons", ""),
        "Validation Warnings": compiled.get("validation_warnings", ""),
    }


def refresh_record(
    processor: BillProcessor,
    fields: dict,
    *,
    apply_eval_expl_fixes: bool = False,
    record_id: str = "",
    refresh: bool = False,
) -> tuple[dict | None, str]:
    url = _record_url(fields)
    if not url:
        return None, "no_url"

    ok, msg = processor.get_doc_text(url, refresh=refresh)
    if not ok:
        return None, f"fetch_failed:{msg}"

    source_text = processor.compiled_bill.get("decoded_text") or ""
    if not source_text or str(source_text).startswith("Error"):
        return None, "empty_source"

    analysis_data = _analysis_from_fields(fields)
    analysis, warnings = validate_bill_analysis(
        analysis_data,
        source_text,
        apply_eval_expl_fixes=apply_eval_expl_fixes,
        record_name=str(fields.get("Name") or ""),
        record_url=url,
    )
    if analysis is None:
        return None, f"analysis_invalid:{'; '.join(warnings)}"

    pros_data = _pros_cons_from_fields(fields)
    pros_cons, pros_warnings = validate_pros_cons(pros_data)
    if pros_cons is None:
        return None, f"pros_invalid:{'; '.join(pros_warnings)}"

    bill_data = dict(fields)
    bill_data["Source"] = fields.get("Source", "")
    consistency = check_record_consistency(bill_data, source_text)
    all_warnings = list(warnings) + list(pros_warnings) + list(consistency.warnings)

    compiled = analysis_to_compiled_fields(analysis, pros_cons, all_warnings)
    updates = _airtable_updates_from_compiled(compiled)
    if not apply_eval_expl_fixes:
        updates["Validation Warnings"] = _strip_eval_expl_fix_warnings(
            updates.get("Validation Warnings", "")
        )

    if consistency.warnings:
        if "Bill Number" in bill_data and bill_data.get("Bill Number") != fields.get("Bill Number"):
            updates["Bill Number"] = bill_data.get("Bill Number", "")
        for key in (
            "Last Update",
            "Sponsors of the Legislation",
            "Chamber Details",
            "Session",
        ):
            if key in bill_data and bill_data.get(key) != fields.get(key):
                updates[key] = bill_data.get(key, "")

    return updates, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--apply-eval-expl-fixes",
        action="store_true",
        help="Adjudicate eval↔expl contradictions and auto-apply safe fixes",
    )
    parser.add_argument(
        "--eval-expl-only",
        action="store_true",
        help="Only process rows with mechanisms/prevention eval↔expl mismatch warnings",
    )
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
        if args.eval_expl_only:
            has_mismatch = (
                "mechanisms_expl provided but mechanisms_eval is not Yes" in warnings
                or "prevention_efforts_expl provided but prevention_efforts_eval is not Yes"
                in warnings
            )
            if not has_mismatch:
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
            updates, status = refresh_record(
                processor,
                fields,
                apply_eval_expl_fixes=args.apply_eval_expl_fixes,
                record_id=rid,
                refresh=args.refresh,
            )
        except Exception as exc:
            logger.exception("Refresh failed for %s: %s", rid, exc)
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
            "[%d/%d] %s warnings: %d -> %d chars",
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
        time.sleep(0.3)

    print(
        f"processed={len(targets)} cleared={cleared} reduced={reduced} "
        f"unchanged={unchanged} failed={failed} apply={args.apply}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
