#!/usr/bin/env python3
"""Refresh the cached indigenous politicians roster from Wikipedia.

Usage:
  python scripts/refresh_indigenous_db.py              # scrape, backup, save
  python scripts/refresh_indigenous_db.py --status     # show cache metadata
  python scripts/refresh_indigenous_db.py --compare A B
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from indigenous_database import DEFAULT_BACKUP_DIR, DEFAULT_DB_PATH, IndigenousDatabase

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def cmd_status(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        print(f"No cache at {path}")
        return 1
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    print(f"path:      {path}")
    print(f"built_at:  {payload.get('built_at')}")
    print(f"count:     {payload.get('count', len(payload.get('politicians') or []))}")
    print(f"source:    {payload.get('source')}")
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    db = IndigenousDatabase(db_path=args.path, backup_dir=args.backup_dir)
    if Path(args.path).is_file():
        db.load_from_disk()
    try:
        stats = db.refresh(min_count=args.min_count)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1
    print(
        f"Refreshed: count={stats['count']} built_at={stats['built_at']} "
        f"backup={stats['backup_path'] or '(none)'} path={stats['path']}"
    )
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    def load_names(path: Path) -> set[str]:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        return {
            (p.get("name") or "").strip()
            for p in payload.get("politicians") or []
            if (p.get("name") or "").strip()
        }

    a = Path(args.before)
    b = Path(args.after)
    names_a = load_names(a)
    names_b = load_names(b)
    added = sorted(names_b - names_a)
    removed = sorted(names_a - names_b)
    print(f"before: {a} ({len(names_a)} names)")
    print(f"after:  {b} ({len(names_b)} names)")
    print(f"added:   {len(added)}")
    for name in added[:50]:
        print(f"  + {name}")
    if len(added) > 50:
        print(f"  ... and {len(added) - 50} more")
    print(f"removed: {len(removed)}")
    for name in removed[:50]:
        print(f"  - {name}")
    if len(removed) > 50:
        print(f"  ... and {len(removed) - 50} more")
    return 0


def cmd_dedupe_only(args: argparse.Namespace) -> int:
    db = IndigenousDatabase(db_path=args.path, backup_dir=args.backup_dir)
    try:
        stats = db.dedupe_disk_cache()
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1
    print(
        f"Deduped: before={stats['before']} after={stats['after']} "
        f"backup={stats['backup_path']} path={stats['path']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Indigenous politicians roster cache")
    parser.add_argument(
        "--path",
        default=str(DEFAULT_DB_PATH),
        help=f"Cache JSON path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help=f"Backup directory (default: {DEFAULT_BACKUP_DIR})",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=None,
        help="Reject scrapes below this count (default: INDIGENOUS_DB_MIN_COUNT or 20)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show metadata for the current cache and exit",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        help="Diff politician names between two cache/backup JSON files",
    )
    parser.add_argument(
        "--dedupe-only",
        action="store_true",
        help="Dedupe the on-disk roster cache without scraping Wikipedia",
    )
    args = parser.parse_args()

    if args.status:
        return cmd_status(args)
    if args.compare:
        args.before, args.after = args.compare
        return cmd_compare(args)
    if args.dedupe_only:
        return cmd_dedupe_only(args)
    return cmd_refresh(args)


if __name__ == "__main__":
    raise SystemExit(main())
