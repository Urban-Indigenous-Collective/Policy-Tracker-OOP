#!/usr/bin/env python3
"""Backup, clear, or compare Airtable Pending table snapshots."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD
from discovery.url_utils import bill_identity_key, normalize_url

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = ROOT / "data" / "backups"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _record_export(record: dict) -> dict:
    return {
        "id": record.get("id"),
        "createdTime": record.get("createdTime"),
        "fields": record.get("fields") or {},
    }


def _fetch_all_pending(client: AirtableClient) -> list[dict]:
    return client.pending_table.all()


def _batch_delete(table, record_ids: list[str], batch_size: int = 10) -> int:
    deleted = 0
    for i in range(0, len(record_ids), batch_size):
        chunk = record_ids[i : i + batch_size]
        table.batch_delete(chunk)
        deleted += len(chunk)
        logger.info("Deleted %d / %d pending records", deleted, len(record_ids))
    return deleted


def cmd_backup(args: argparse.Namespace) -> int:
    load_dotenv(ROOT / ".env")
    client = AirtableClient()
    records = _fetch_all_pending(client)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = args.label or _utc_stamp()
    out_path = out_dir / f"pending-{stamp}.json"
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "table": client.pending_table_name,
        "record_count": len(records),
        "records": [_record_export(r) for r in records],
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Backed up {len(records)} Pending record(s) to {out_path}")
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    if not args.confirm:
        print("Refusing to clear Pending without --confirm")
        return 1
    load_dotenv(ROOT / ".env")
    client = AirtableClient()
    records = _fetch_all_pending(client)
    if not records:
        print("Pending table is already empty")
        return 0
    if args.limit and args.limit > 0:
        records = records[: args.limit]
    ids = [r["id"] for r in records if r.get("id")]
    deleted = _batch_delete(client.pending_table, ids)
    print(f"Cleared {deleted} Pending record(s) from {client.pending_table_name}")
    return 0


def _identity(record: dict) -> str:
    fields = record.get("fields") or {}
    url = fields.get(BILL_OVERVIEW_LINK_FIELD) or fields.get("Bill Overview") or ""
    normalized = normalize_url(url) if url else ""
    if normalized:
        return f"url:{normalized}"
    key = bill_identity_key(fields.get("State", ""), fields.get("Bill Number", ""))
    if key:
        return f"bill:{key[0]}:{key[1]}"
    return f"id:{record.get('id', 'unknown')}"


def _index_records(records: list[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for record in records:
        indexed[_identity(record)] = record
    return indexed


def _field_diff(old_fields: dict, new_fields: dict, keys: list[str]) -> dict[str, dict]:
    diff: dict[str, dict] = {}
    for key in keys:
        old_val = old_fields.get(key)
        new_val = new_fields.get(key)
        if old_val != new_val:
            diff[key] = {"old": old_val, "new": new_val}
    return diff


def cmd_compare(args: argparse.Namespace) -> int:
    before = json.loads(Path(args.before).read_text())
    after = json.loads(Path(args.after).read_text())
    before_records = before.get("records") or []
    after_records = after.get("records") or []
    before_idx = _index_records(before_records)
    after_idx = _index_records(after_records)

    only_before = sorted(set(before_idx) - set(after_idx))
    only_after = sorted(set(after_idx) - set(before_idx))
    shared = sorted(set(before_idx) & set(after_idx))

    compare_fields = [
        "Review Status",
        "Source",
        "Relevance Confidence",
        "Relevance Rationale",
        "State",
        "Bill Number",
        "Bill Title",
        BILL_OVERVIEW_LINK_FIELD,
    ]
    changed: list[dict] = []
    for key in shared:
        old_fields = before_idx[key].get("fields") or {}
        new_fields = after_idx[key].get("fields") or {}
        diff = _field_diff(old_fields, new_fields, compare_fields)
        if diff:
            changed.append({"identity": key, "diff": diff})

    report = {
        "before_file": str(args.before),
        "after_file": str(args.after),
        "before_count": len(before_records),
        "after_count": len(after_records),
        "only_in_before": len(only_before),
        "only_in_after": len(only_after),
        "shared": len(shared),
        "changed_on_shared": len(changed),
        "only_before_identities": only_before[: args.max_list],
        "only_after_identities": only_after[: args.max_list],
        "changed": changed[: args.max_list],
    }
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Wrote comparison report to {args.output}")
    else:
        print(json.dumps(report, indent=2))

    print(
        f"\nSummary: before={len(before_records)} after={len(after_records)} "
        f"removed={len(only_before)} added={len(only_after)} changed={len(changed)}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pending table backup / clear / compare")
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="Export all Pending rows to JSON")
    backup.add_argument(
        "--output-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help="Directory for snapshot files (default: data/backups)",
    )
    backup.add_argument("--label", default="", help="Optional filename suffix (default: UTC timestamp)")
    backup.set_defaults(func=cmd_backup)

    clear = sub.add_parser("clear", help="Delete all Pending rows (requires --confirm)")
    clear.add_argument("--confirm", action="store_true", help="Required safety flag")
    clear.add_argument("--limit", type=int, default=0, help="Delete at most N records (testing)")
    clear.set_defaults(func=cmd_clear)

    compare = sub.add_parser("compare", help="Diff two pending backup JSON files")
    compare.add_argument("before", help="Path to older snapshot JSON")
    compare.add_argument("after", help="Path to newer snapshot JSON")
    compare.add_argument("--output", default="", help="Write full report JSON here")
    compare.add_argument("--max-list", type=int, default=200, help="Cap listed identities/changes")
    compare.set_defaults(func=cmd_compare)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
