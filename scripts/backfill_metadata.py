#!/usr/bin/env python3
"""Backfill missing Last Update and Session fields on Pending / Main v3.

Strategies (in priority order per record):
  1. LegiScan getBill API — authoritative for LegiScan rows
  2. Restore from pre-clear backup JSON — for Federal / State rows cleared by
     content_guard before Federal Site session skip was added
  3. Federal administration from grounded Last Update date — only when session
     is still empty and the date maps to a known presidential term

Usage:
  python scripts/backfill_metadata.py
  python scripts/backfill_metadata.py --apply
  python scripts/backfill_metadata.py --table pending --apply
  python scripts/backfill_metadata.py --backup data/backups/pending-pre-indigenous-sponsor-backfill.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, REVIEW_STATUS_REJECTED
from api_client import APIClient
from discovery.status_refresh import _year_from_fields
from legiscan_processor import LegiScanProcessor, parse_legiscan_bill_url

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

DEFAULT_PENDING_BACKUP = Path("data/backups/pending-pre-indigenous-sponsor-backfill.json")
DEFAULT_LIVE_BACKUP = Path("data/backups/live-pre-indigenous-sponsor-backfill.json")

CLEARED_LU = re.compile(r"Last Update .*not grounded.*cleared", re.I)
CLEARED_SE = re.compile(r"Session .*not grounded.*cleared", re.I)

# Presidential terms for federal DOJ / White House / Federal Register documents.
# Not used for congressional bills (those should use LegiScan session_title).
PRESIDENTIAL_TERMS: list[tuple[str, dt.date, dt.date]] = [
    ("Obama Administration", dt.date(2009, 1, 20), dt.date(2017, 1, 20)),
    ("Trump Administration", dt.date(2017, 1, 20), dt.date(2021, 1, 20)),
    ("Biden Administration", dt.date(2021, 1, 20), dt.date(2025, 1, 20)),
    ("Trump Administration", dt.date(2025, 1, 20), dt.date(2033, 1, 20)),
]


@dataclass
class BackfillStats:
    scanned: int = 0
    would_update: int = 0
    applied: int = 0
    legiscan_api: int = 0
    backup_restore: int = 0
    federal_admin: int = 0
    skipped: int = 0
    unresolved: int = 0
    by_source: Counter = field(default_factory=Counter)
    field_counts: Counter = field(default_factory=Counter)


def _record_url(fields: dict) -> str:
    return (
        fields.get(BILL_OVERVIEW_LINK_FIELD)
        or fields.get("Bill Overview")
        or fields.get("Bill Text")
        or ""
    )


def _infer_source(fields: dict, url: str) -> str:
    source = str(fields.get("Source") or "").strip()
    if source:
        return source
    lower = (url or "").lower()
    if "legiscan.com" in lower:
        return "LegiScan"
    if any(x in lower for x in ("whitehouse.gov", "justice.gov", "federalregister.gov", "govinfo.gov")):
        return "Federal Site"
    if ".gov" in lower:
        return "State Site"
    return "(unknown)"


def _load_backup(path: Path) -> dict[str, dict]:
    if not path.exists():
        logger.warning("Backup not found: %s", path)
        return {}
    payload = json.loads(path.read_text())
    records = payload.get("records") if isinstance(payload, dict) else payload
    return {r["id"]: r.get("fields") or {} for r in records}


def _parse_date(value: str) -> dt.date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def administration_from_date(value: str) -> str:
    """Map an ISO date string to the presidential administration in office."""
    day = _parse_date(value)
    if not day:
        return ""
    for name, start, end in PRESIDENTIAL_TERMS:
        if start <= day < end:
            return name
    return ""


_presidential_administration = administration_from_date


def _needs_backfill(fields: dict) -> bool:
    return not str(fields.get("Last Update") or "").strip() or not str(
        fields.get("Session") or ""
    ).strip()


def _legiscan_updates(
    legiscan: LegiScanProcessor,
    api: APIClient,
    fields: dict,
    url: str,
) -> tuple[dict, str]:
    year = _year_from_fields(fields, url)
    state = str(fields.get("State") or "").strip()
    bill_number = str(fields.get("Bill Number") or "").strip()
    bill_id = legiscan.resolve_bill_id(url, state=state, bill_number=bill_number, year=year)
    if not bill_id:
        return {}, "unresolved_bill_id"
    details = api.get_bill_details(bill_id)
    if not details or not isinstance(details, dict) or "bill" not in details:
        return {}, "getbill_failed"
    meta = legiscan.extract_metadata_fields(details)
    updates: dict[str, str] = {}
    if not str(fields.get("Last Update") or "").strip() and meta.get("Last Update"):
        updates["Last Update"] = meta["Last Update"]
    if not str(fields.get("Session") or "").strip() and meta.get("Session"):
        updates["Session"] = meta["Session"]
    if not updates:
        return {}, "unchanged"
    return updates, "legiscan_api"


def _backup_updates(fields: dict, backup_fields: dict) -> dict:
    updates: dict[str, str] = {}
    if not str(fields.get("Last Update") or "").strip():
        old = str(backup_fields.get("Last Update") or "").strip()
        if old:
            updates["Last Update"] = old
    if not str(fields.get("Session") or "").strip():
        old = str(backup_fields.get("Session") or "").strip()
        if old:
            updates["Session"] = old
    return updates


def _federal_session_update(fields: dict, updates: dict, url: str = "") -> dict:
    if str(fields.get("Session") or "").strip() or updates.get("Session"):
        return updates
    if _infer_source(fields, url or _record_url(fields)) != "Federal Site":
        return updates
    date_val = updates.get("Last Update") or fields.get("Last Update") or ""
    admin = administration_from_date(str(date_val))
    if admin:
        updates = dict(updates)
        updates["Session"] = admin
    return updates


def backfill_record(
    record: dict,
    *,
    legiscan: LegiScanProcessor,
    api: APIClient,
    backup_by_id: dict[str, dict],
    allow_federal_admin: bool,
) -> tuple[dict, str]:
    fields = record.get("fields") or {}
    if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
        return {}, "rejected"
    if not _needs_backfill(fields):
        return {}, "complete"

    url = _record_url(fields)
    source = _infer_source(fields, url)
    updates: dict[str, str] = {}
    reason = "skipped"

    if source == "LegiScan" and url and legiscan.is_legiscan_url(url):
        updates, reason = _legiscan_updates(legiscan, api, fields, url)

    backup = backup_by_id.get(record["id"], {})
    if backup:
        backup_updates = _backup_updates(fields, backup)
        for key, value in backup_updates.items():
            if key not in updates and not str(fields.get(key) or "").strip():
                updates[key] = value
                if reason in ("skipped", "unchanged", "unresolved_bill_id", "getbill_failed"):
                    reason = "backup_restore"

    if allow_federal_admin and source == "Federal Site":
        before = updates.get("Session")
        updates = _federal_session_update(fields, updates, url)
        if not before and updates.get("Session"):
            reason = "federal_admin" if reason == "skipped" else reason

    # Never overwrite existing values.
    updates = {
        key: value
        for key, value in updates.items()
        if value and not str(fields.get(key) or "").strip()
    }
    if not updates:
        return {}, reason
    return updates, reason


def _print_summary(stats: BackfillStats, apply: bool) -> None:
    print(
        f"scanned={stats.scanned} would_update={stats.would_update} applied={stats.applied} "
        f"legiscan_api={stats.legiscan_api} backup_restore={stats.backup_restore} "
        f"federal_admin={stats.federal_admin} skipped={stats.skipped} unresolved={stats.unresolved} "
        f"apply={apply}"
    )
    if stats.field_counts:
        print("fields:", dict(stats.field_counts))
    if stats.by_source:
        print("by_source:", dict(stats.by_source))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--table", choices=("pending", "live", "both"), default="both")
    parser.add_argument("--backup", action="append", default=[], help="Backup JSON (repeatable)")
    parser.add_argument(
        "--no-federal-admin",
        action="store_true",
        help="Do not derive presidential administration from Last Update date",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--record-id", action="append", default=[])
    args = parser.parse_args()

    backup_paths = [Path(p) for p in args.backup]
    if not backup_paths:
        backup_paths = [DEFAULT_PENDING_BACKUP, DEFAULT_LIVE_BACKUP]

    backup_by_id: dict[str, dict] = {}
    for path in backup_paths:
        backup_by_id.update(_load_backup(path))

    api = APIClient(os.environ["LEGISCAN_KEY"])
    legiscan = LegiScanProcessor(indigenous_db=None, api_client=api)
    client = AirtableClient()

    targets: list[tuple[str, object, object]] = []
    if args.table in ("pending", "both"):
        targets.append(("Pending", client.pending_table, client.pending_table))
    if args.table in ("live", "both"):
        targets.append(("Main v3", client.live_table, client.live_table))

    stats = BackfillStats()
    allow_federal_admin = not args.no_federal_admin

    for table_label, table, write_table in targets:
        for record in table.all():
            if args.record_id and record["id"] not in args.record_id:
                continue
            fields = record.get("fields") or {}
            if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
                continue
            if not _needs_backfill(fields):
                continue

            stats.scanned += 1
            if args.limit and stats.scanned > args.limit:
                break

            updates, reason = backfill_record(
                record,
                legiscan=legiscan,
                api=api,
                backup_by_id=backup_by_id,
                allow_federal_admin=allow_federal_admin,
            )

            if reason in ("skipped", "complete", "rejected", "unchanged"):
                stats.skipped += 1
                continue
            if reason in ("unresolved_bill_id", "getbill_failed"):
                stats.unresolved += 1
                logger.warning(
                    "%s %s unresolved (%s): %s",
                    table_label,
                    record["id"],
                    reason,
                    (fields.get("Name") or "")[:60],
                )
                continue

            stats.would_update += 1
            stats.by_source[_infer_source(fields, _record_url(fields))] += 1
            if reason == "legiscan_api":
                stats.legiscan_api += 1
            elif reason == "backup_restore":
                stats.backup_restore += 1
            elif reason == "federal_admin":
                stats.federal_admin += 1
            for key in updates:
                stats.field_counts[key] += 1

            logger.info(
                "%s %s %s via %s: %s",
                table_label,
                record["id"],
                (fields.get("Name") or "")[:50],
                reason,
                updates,
            )

            if args.apply:
                client.update_record(write_table, record["id"], updates)
                stats.applied += 1
            time.sleep(0.25)

    _print_summary(stats, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
