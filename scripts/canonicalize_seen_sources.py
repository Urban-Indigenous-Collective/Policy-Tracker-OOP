#!/usr/bin/env python3
"""Dry-run migration: normalize seen_candidates.source to canonical spellings.

Maps Airtable display labels ("LegiScan", "State Site") and loose variants to
legiscan / state_site / federal_site. Idempotent — re-running after a successful
apply is a no-op.

Default is dry-run. Pass --confirm to write changes. Do not run against production
without reviewing the dry-run output first.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.seen_store import CANONICAL_SOURCES, canonical_source


def _plan(conn: sqlite3.Connection) -> list[tuple[str, str, int]]:
    rows = conn.execute(
        "SELECT source, COUNT(*) FROM seen_candidates GROUP BY source ORDER BY 2 DESC"
    ).fetchall()
    plan: list[tuple[str, str, int]] = []
    for source, count in rows:
        canonical = canonical_source(source or "")
        if canonical and canonical in CANONICAL_SOURCES and canonical != source:
            plan.append((source, canonical, count))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"),
        help="Path to discovery SQLite database",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Apply updates (default: dry run only)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    plan = _plan(conn)
    if not plan:
        print("No source labels need canonicalization.")
        return 0

    total = sum(count for _, _, count in plan)
    print(f"{'APPLY' if args.confirm else 'DRY RUN'}: {total} row(s) across {len(plan)} label(s)\n")
    for old, new, count in plan:
        print(f"  {old!r} -> {new!r}: {count}")

    if not args.confirm:
        print("\nRe-run with --confirm to apply.")
        return 0

    updated = 0
    for old, new, _ in plan:
        cur = conn.execute(
            "UPDATE seen_candidates SET source = ? WHERE source = ?", (new, old)
        )
        updated += cur.rowcount
    conn.commit()
    print(f"\nUpdated {updated} row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
