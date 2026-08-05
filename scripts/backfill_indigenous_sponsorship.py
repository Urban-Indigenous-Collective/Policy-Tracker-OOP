#!/usr/bin/env python3
"""Recompute Indigenous Sponsorship from Sponsors using the current roster matcher.

Safe by default (dry-run). Pass ``--apply`` to write Airtable updates.

Usage:
  python scripts/backfill_indigenous_sponsorship.py
  python scripts/backfill_indigenous_sponsorship.py --tables pending,live --apply
  python scripts/backfill_indigenous_sponsorship.py --limit 50
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from airtable_client import AirtableClient
from indigenous_database import IndigenousDatabase
from sponsor_utils import process_sponsors

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SPONSORS_FIELD = "Sponsors of the Legislation"
INDIGENOUS_FIELD = "Indigenous Sponsorship"

# Keep party tags like (D)/(R)/(I); strip other parentheticals (e.g. prior tribe labels)
# so re-annotation does not double-wrap ethnicity.
_NON_PARTY_PAREN = re.compile(r"\(([^)]*)\)")
_PARTY_TAG = re.compile(r"^[DRI](-[A-Za-z]+)?$", re.I)


def _strip_non_party_parens(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        inner = (match.group(1) or "").strip()
        if _PARTY_TAG.fullmatch(inner):
            return match.group(0)
        return ""

    cleaned = _NON_PARTY_PAREN.sub(repl, text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _normalize_field(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _recompute(sponsors_raw: str, indigenous_db: IndigenousDatabase) -> tuple[str, str]:
    cleaned = _strip_non_party_parens(sponsors_raw)
    return process_sponsors(cleaned, indigenous_db)


def _iter_tables(client: AirtableClient, tables: list[str]):
    mapping = {
        "pending": (client.pending_table_name, client.pending_table),
        "live": (client.live_table_name, client.live_table),
    }
    for key in tables:
        if key not in mapping:
            raise ValueError(f"Unknown table key {key!r}; use pending and/or live")
        yield key, mapping[key][0], mapping[key][1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tables",
        default="pending,live",
        help="Comma-separated: pending, live (default: both)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write Indigenous Sponsorship updates to Airtable (default: dry-run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max records to update per table (0 = no limit)",
    )
    parser.add_argument(
        "--also-sponsors",
        action="store_true",
        help="Also rewrite Sponsors of the Legislation with ethnicity annotations",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=40,
        help="Max change examples to print (default: 40)",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    tables = [t.strip().lower() for t in args.tables.split(",") if t.strip()]
    if not tables:
        print("No tables selected")
        return 1

    indigenous_db = IndigenousDatabase()
    source = indigenous_db.ensure_loaded()
    built_at = str(indigenous_db.built_at or "unknown")
    logger.info(
        "Indigenous roster loaded via %s (count=%d built_at=%s)",
        source,
        len(indigenous_db.database),
        built_at,
    )

    client = AirtableClient()
    total_scanned = 0
    total_changed = 0
    total_written = 0
    examples: list[str] = []

    for table_key, table_label, table in _iter_tables(client, tables):
        records = table.all()
        changed_here = 0
        scanned_here = 0
        print(f"\n=== {table_label} ({table_key}) — {len(records)} record(s) ===")

        for record in records:
            if args.limit and changed_here >= args.limit:
                break

            fields = record.get("fields") or {}
            sponsors_raw = _normalize_field(fields.get(SPONSORS_FIELD))
            if not sponsors_raw:
                continue

            scanned_here += 1
            total_scanned += 1
            new_sponsors, new_indigenous = _recompute(sponsors_raw, indigenous_db)
            old_indigenous = _normalize_field(fields.get(INDIGENOUS_FIELD))
            old_sponsors = sponsors_raw

            updates: dict[str, str] = {}
            if new_indigenous != old_indigenous:
                updates[INDIGENOUS_FIELD] = new_indigenous
            if args.also_sponsors and new_sponsors != old_sponsors:
                updates[SPONSORS_FIELD] = new_sponsors

            if not updates:
                continue

            changed_here += 1
            total_changed += 1
            name = _normalize_field(fields.get("Name"))[:70]
            bill = _normalize_field(fields.get("Bill Number"))
            state = _normalize_field(fields.get("State"))
            summary = (
                f"[{table_key}] {record['id']} {state} {bill} {name!r}\n"
                f"    old indigenous: {old_indigenous!r}\n"
                f"    new indigenous: {new_indigenous!r}"
            )
            if SPONSORS_FIELD in updates:
                summary += (
                    f"\n    old sponsors: {old_sponsors[:120]!r}"
                    f"\n    new sponsors: {new_sponsors[:120]!r}"
                )
            if len(examples) < args.show:
                examples.append(summary)

            if args.apply:
                client.update_record(table, record["id"], updates)
                total_written += 1
                logger.info("Updated %s %s", table_key, record["id"])

        print(f"Scanned with sponsors: {scanned_here}; would change / changed: {changed_here}")

    print("\n=== Summary ===")
    print(f"Scanned (with sponsors): {total_scanned}")
    print(f"Changes: {total_changed}")
    if args.apply:
        print(f"Written: {total_written}")
    else:
        print("Dry-run only — re-run with --apply to write.")

    if examples:
        print(f"\n=== Examples ({len(examples)}) ===")
        for line in examples:
            print(line)
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
