#!/usr/bin/env python3
"""Backup Main v3 (Live) Airtable table snapshots with retention cleanup."""

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

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = ROOT / "data" / "backups"
DEFAULT_KEEP_FILES = 30
LIVE_BACKUP_PREFIX = "live-"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _record_export(record: dict) -> dict:
    return {
        "id": record.get("id"),
        "createdTime": record.get("createdTime"),
        "fields": record.get("fields") or {},
    }


def cleanup_old_backups(output_dir: Path, keep: int = DEFAULT_KEEP_FILES) -> int:
    """Delete oldest live-*.json backups, keeping the newest ``keep`` files."""
    if keep <= 0:
        return 0
    files = sorted(
        output_dir.glob(f"{LIVE_BACKUP_PREFIX}*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for path in files[keep:]:
        path.unlink(missing_ok=True)
        removed += 1
        logger.info("Removed old live backup: %s", path.name)
    return removed


def backup_live_table(
    output_dir: Path | None = None,
    *,
    label: str = "",
    keep: int = DEFAULT_KEEP_FILES,
) -> Path:
    """Export all Live (Main v3) rows to JSON and prune old backups."""
    out_dir = output_dir or DEFAULT_BACKUP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    client = AirtableClient()
    records = client.all_live_records()
    stamp = label or _utc_stamp()
    out_path = out_dir / f"{LIVE_BACKUP_PREFIX}{stamp}.json"
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "table": client.live_table_name,
        "record_count": len(records),
        "records": [_record_export(r) for r in records],
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Backed up %d Live record(s) to %s (%.1f KB)",
        len(records),
        out_path,
        out_path.stat().st_size / 1024,
    )

    removed = cleanup_old_backups(out_dir, keep=keep)
    if removed:
        logger.info("Retention cleanup removed %d old live backup(s)", removed)
    return out_path


def cmd_backup(args: argparse.Namespace) -> int:
    load_dotenv(ROOT / ".env")
    out_path = backup_live_table(
        Path(args.output_dir),
        label=args.label,
        keep=args.keep,
    )
    print(f"Backed up Live table to {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live (Main v3) table backup")
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="Export all Live rows to JSON")
    backup.add_argument(
        "--output-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help="Directory for snapshot files (default: data/backups)",
    )
    backup.add_argument("--label", default="", help="Optional filename suffix (default: UTC timestamp)")
    backup.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_KEEP_FILES,
        help=f"Retain newest N live backup files (default: {DEFAULT_KEEP_FILES})",
    )
    backup.set_defaults(func=cmd_backup)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
