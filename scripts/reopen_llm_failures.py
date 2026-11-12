#!/usr/bin/env python3
"""Reopen discovery seen_candidates stuck after LLM infrastructure failures.

Deletes rows where:
  - verdict IN ('llm_error', 'llm_fail'), or
  - status = 'error' (processing/infrastructure failures)

Does NOT touch genuine not-MMIP rejects (verdict='llm') or other terminal rejects.

Dry-run by default. Apply with --apply.

Prod example:
  docker compose exec scheduler python scripts/reopen_llm_failures.py
  docker compose exec scheduler python scripts/reopen_llm_failures.py --apply
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RETRYABLE_VERDICTS = ("llm_error", "llm_fail")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _select_stuck(conn: sqlite3.Connection, include_error_status: bool) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in RETRYABLE_VERDICTS)
    sql = f"""
        SELECT url, source, state, status, verdict
        FROM seen_candidates
        WHERE verdict IN ({placeholders})
    """
    params: list[str] = list(RETRYABLE_VERDICTS)
    if include_error_status:
        sql += " OR status = 'error'"
    sql += " ORDER BY status, verdict, url"
    return list(conn.execute(sql, params))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"),
        help="Path to discovery.db (default: DISCOVERY_DB_PATH or data/discovery.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete matching rows (default is dry-run)",
    )
    parser.add_argument(
        "--no-error-status",
        action="store_true",
        help="Only reopen llm_error/llm_fail verdicts; leave status=error alone",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max rows to show/delete (0 = all)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 1

    include_error = not args.no_error_status
    with _connect(str(db_path)) as conn:
        rows = _select_stuck(conn, include_error_status=include_error)
        if args.limit and args.limit > 0:
            rows = rows[: args.limit]

        by_key: dict[str, int] = {}
        for row in rows:
            key = f"status={row['status']}|verdict={row['verdict'] or ''}"
            by_key[key] = by_key.get(key, 0) + 1

        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"[{mode}] db={db_path}")
        print(f"matched={len(rows)} (include status=error: {include_error})")
        for key, count in sorted(by_key.items()):
            print(f"  {key}: {count}")
        for row in rows[:20]:
            print(
                f"  sample: {row['status']:10} {row['verdict'] or '':12} "
                f"{row['state'] or '':3} {row['url']}"
            )
        if len(rows) > 20:
            print(f"  ... and {len(rows) - 20} more")

        if not args.apply:
            print("No changes written. Re-run with --apply to delete these rows.")
            return 0

        if not rows:
            print("Nothing to reopen.")
            return 0

        urls = [row["url"] for row in rows]
        deleted = 0
        for url in urls:
            cur = conn.execute("DELETE FROM seen_candidates WHERE url = ?", (url,))
            deleted += cur.rowcount
        conn.commit()
        print(f"Deleted {deleted} seen_candidates row(s). Next discovery run will retry them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
