#!/usr/bin/env python3
"""Repair Pending records with mangled or empty Categories.

Finds non-rejected Pending rows whose Categories were comma-split from a
Python-list string repr (e.g. ``['Day of Recognition', 'US Law Enforcement']``)
or contain invalid multi-select tokens, and rewrites them to valid values.

Typical root cause: a comma-separated list repr was written to Airtable's
multi-select field with ``typecast=True`` before ``coerce_categories`` ran,
so Airtable split on commas inside the brackets/quotes.

Usage:
  python scripts/fix_mangled_categories.py              # dry-run
  python scripts/fix_mangled_categories.py --apply      # write to Airtable
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_coercion import coerce_categories
from airtable_fields import REVIEW_STATUS_REJECTED
from analysis_validator import validate_categories

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_MANGLED_TOKEN_RE = re.compile(r"[\[\]'\"]")
_INVALID_CATEGORY_WARNING = re.compile(r"Invalid category:")


def _strip_invalid_category_warnings(warnings: str) -> str:
    parts = [p.strip() for p in str(warnings or "").split(";") if p.strip()]
    kept = [p for p in parts if not p.startswith("Invalid category:")]
    return "; ".join(kept)


def _categories_look_mangled(categories: list[str]) -> bool:
    if not categories:
        return False
    return any(_MANGLED_TOKEN_RE.search(cat) for cat in categories)


def _has_invalid_category_warning(warnings: str) -> bool:
    return bool(_INVALID_CATEGORY_WARNING.search(str(warnings or "")))


def discover_mangled_records(client: AirtableClient) -> list[dict]:
    targets: list[dict] = []
    for record in client.pending_table.all():
        fields = record.get("fields") or {}
        if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
            continue

        old_cats = fields.get("Categories") or []
        if not isinstance(old_cats, list):
            old_cats = [str(old_cats)] if old_cats else []

        warnings = str(fields.get("Validation Warnings") or "")
        invalid_cats = validate_categories(old_cats)
        if (
            not _categories_look_mangled(old_cats)
            and not invalid_cats
            and not _has_invalid_category_warning(warnings)
        ):
            continue

        fixed_cats = coerce_categories(old_cats)
        if not fixed_cats:
            continue
        if fixed_cats == old_cats and not invalid_cats and not _has_invalid_category_warning(warnings):
            continue

        targets.append(
            {
                "record_id": record["id"],
                "name": str(fields.get("Name") or record["id"])[:80],
                "state": fields.get("State") or "",
                "source": fields.get("Source") or "",
                "discovered_on": fields.get("Discovered On") or "",
                "old_categories": old_cats,
                "categories": fixed_cats,
                "old_warnings": warnings,
            }
        )
    return targets


def build_repair_updates(target: dict) -> dict:
    updates: dict = {"Categories": target["categories"]}
    revised_warnings = _strip_invalid_category_warnings(target.get("old_warnings", ""))
    if revised_warnings != str(target.get("old_warnings") or "").strip():
        updates["Validation Warnings"] = revised_warnings
    return updates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    client = AirtableClient()
    targets = discover_mangled_records(client)

    if not targets:
        print("No mangled category records found.")
        return 0

    reports = []
    repaired = 0
    skipped = 0

    for target in targets:
        rid = target["record_id"]
        old_cats = target["old_categories"]
        fixed_cats = target["categories"]

        if validate_categories(fixed_cats):
            logger.error("%s fixed categories still invalid: %s", rid, fixed_cats)
            reports.append({**target, "error": "fixed categories still invalid"})
            skipped += 1
            continue

        updates = build_repair_updates(target)
        report = {
            "record_id": rid,
            "name": target["name"],
            "state": target.get("state", ""),
            "source": target.get("source", ""),
            "discovered_on": target.get("discovered_on", ""),
            "old_categories": old_cats,
            "categories": fixed_cats,
            "old_warnings": target.get("old_warnings", ""),
            "new_warnings": updates.get("Validation Warnings", target.get("old_warnings", "")),
            "method": "coerce",
        }
        reports.append(report)
        repaired += 1

        print(
            f"{'APPLY' if args.apply else 'DRY-RUN'} {rid} ({target['name']})\n"
            f"  source={target.get('source', '')} discovered={target.get('discovered_on', '')}\n"
            f"  old={old_cats!r}\n"
            f"  new={fixed_cats!r}\n"
            f"  warnings: {len(str(target.get('old_warnings') or ''))} -> "
            f"{len(str(updates.get('Validation Warnings', target.get('old_warnings') or '')))} chars"
        )

        if args.apply:
            client.update_record(client.pending_table, rid, updates)

    print(json.dumps(reports, indent=2))
    print(f"repaired={repaired} skipped={skipped} apply={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
