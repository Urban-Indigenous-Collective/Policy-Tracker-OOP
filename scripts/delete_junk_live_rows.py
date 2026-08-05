#!/usr/bin/env python3
"""Delete verified junk rows from Main v3 (Live) Airtable.

Targets rows audited in b38c98f1 investigation: Name="No Results" placeholders
and the blank KS row (recCfLBYNI6fKaL1Y). Re-verifies each record before delete
and skips rows that gained real content.

Dry-run by default. Takes a live_snapshot backup before deleting when --confirm.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD
from scripts.live_snapshot import backup_live_table

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# b38c98f1 investigation — 28 "No Results" + 1 blank KS row
DEFAULT_JUNK_IDS = [
    "reckXGtZfVzCKWhzq",
    "recuscGf0Qpfu73bP",
    "recHmItCgMFCkxyJr",
    "rece4Z7cibfewd3Av",
    "recU72ZidLNd30HpV",
    "recpQADsz63IcWCyc",
    "recad6Dxv2AyrgDhv",
    "recHvCYcvSDdlUy7O",
    "recuB8OaLwt00y3dQ",
    "recpdLKa0suHXaWtU",
    "recCfLBYNI6fKaL1Y",
    "recX79NFiS9HJwito",
    "recnFSsxAF8e7Jrqn",
    "recVaqBhvfHbjfhfr",
    "recw4XAOvnXUinqkk",
    "rec3Pt7EUZvpT3rQI",
    "rec0j0hzDqIo5ANOD",
    "recxfQusbkEYQRpnc",
    "recOcT6lXS8WLiJjI",
    "recNlSdoi3aSa1K0u",
    "recPt3OvYla04IJUC",
    "recLGbOK20tVTNgcr",
    "rechewEAbLopr1n7x",
    "recWDveS4gmz8CoUg",
    "reckNkIn1b0yQ72kG",
    "recjU0HfWMBax0Ytz",
    "recJc4O2ZpC1OPILH",
    "recGev46QQstfOUGi",
    "recXPxGmhbTuiasw6",
]

# Legacy URL-less real rows + known real bills — never delete
PROTECTED_IDS = frozenset(
    {
        "recpfSogk3deEgySf",  # WA legacy
        "recsalKAAHC2nRfDL",  # MT legacy
        "recpYdguR4FA2d3EE",  # WI legacy
        "recNYDvLVnvDCWjnx",  # OR legacy
        "recLODwsvXNz84a0m",  # NE real bill (Nebraska MMIP Study)
    }
)

CONTENT_FIELDS = (
    "Summary",
    "Bill Text",
    "Bill Overview",
    BILL_OVERVIEW_LINK_FIELD,
    "Bill Number",
    "Title",
    "Optional Link",
    "Sponsors",
    "Categories",
)


def _load_ids(args: argparse.Namespace) -> list[str]:
    ids = list(args.record_ids) if args.record_ids else list(DEFAULT_JUNK_IDS)
    if args.ids_file:
        ids.extend(
            line.strip()
            for line in Path(args.ids_file).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )
    seen: set[str] = set()
    return [rid for rid in ids if not (rid in seen or seen.add(rid))]


def _has_real_content(fields: dict) -> bool:
    for key in CONTENT_FIELDS:
        value = fields.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if key in ("Title", "Name") and text.lower() == "no results":
            continue
        return True
    return False


def is_junk(fields: dict, record_id: str) -> tuple[bool, str]:
    """Return (should_delete, reason)."""
    if record_id in PROTECTED_IDS:
        return False, "protected record"

    if _has_real_content(fields):
        return False, "has real content"

    name = str(fields.get("Name") or "").strip()
    if name == "No Results":
        return True, "Name=No Results"

    state = str(fields.get("State") or "").strip()
    if not name and state and not str(fields.get("Bill Number") or "").strip():
        return True, f"blank name, State={state} only"

    return False, "does not match junk criteria"


def _batch_delete(table, record_ids: list[str], batch_size: int = 10) -> int:
    deleted = 0
    for i in range(0, len(record_ids), batch_size):
        chunk = record_ids[i : i + batch_size]
        table.batch_delete(chunk)
        deleted += len(chunk)
        logger.info("Deleted %d / %d live records", deleted, len(record_ids))
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "record_ids",
        nargs="*",
        help="Airtable Live record ids (default: b38c98f1 junk list)",
    )
    parser.add_argument("--ids-file", default="", help="File with one record id per line")
    parser.add_argument("--confirm", action="store_true", help="Apply deletes (default: dry run)")
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip live_snapshot backup (not recommended with --confirm)",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Write JSON audit report to this path",
    )
    args = parser.parse_args()

    record_ids = _load_ids(args)
    if not record_ids:
        parser.error("no record ids provided")

    load_dotenv(ROOT / ".env")
    client = AirtableClient()

    to_delete: list[str] = []
    skipped: list[dict] = []
    missing: list[str] = []
    verified: list[dict] = []

    for record_id in record_ids:
        try:
            record = client.live_table.get(record_id)
        except Exception as exc:
            logger.warning("%s: could not read (%s)", record_id, exc)
            missing.append(record_id)
            continue

        fields = record.get("fields") or {}
        junk, reason = is_junk(fields, record_id)
        entry = {
            "record_id": record_id,
            "state": fields.get("State"),
            "name": fields.get("Name"),
            "reason": reason,
            "junk": junk,
        }
        verified.append(entry)

        label = f"{record_id} [{fields.get('State', '?')}] {str(fields.get('Name') or '(blank)')[:60]}"
        if junk:
            to_delete.append(record_id)
            logger.info("VERIFY OK delete: %s — %s", label, reason)
        else:
            skipped.append(entry)
            logger.info("SKIP: %s — %s", label, reason)

    backup_path: Path | None = None
    deleted = 0

    if args.confirm and to_delete:
        if not args.skip_backup:
            backup_path = backup_live_table(label=f"pre-junk-delete-{_utc_stamp()}")
            logger.info("Backup before delete: %s", backup_path)
        deleted = _batch_delete(client.live_table, to_delete)
    elif to_delete:
        for record_id in to_delete:
            entry = next(v for v in verified if v["record_id"] == record_id)
            print(
                f"DRY RUN would delete {record_id} "
                f"[{entry.get('state')}] {entry.get('name') or '(blank)'} — {entry['reason']}"
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": not args.confirm,
        "backup_path": str(backup_path) if backup_path else None,
        "requested": len(record_ids),
        "verified_junk": len(to_delete),
        "deleted": deleted,
        "skipped": len(skipped),
        "missing": len(missing),
        "verified": verified,
        "skipped_details": skipped,
        "missing_ids": missing,
        "deleted_ids": to_delete if args.confirm else [],
    }

    report_path = Path(args.report) if args.report else None
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.info("Wrote audit report to %s", report_path)

    print(
        f"{'Deleted' if args.confirm else 'Would delete'} {len(to_delete)} junk row(s); "
        f"skipped {len(skipped)}; missing {len(missing)}"
    )
    if backup_path:
        print(f"Backup: {backup_path}")
    if report_path:
        print(f"Report: {report_path}")

    return 0


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
