#!/usr/bin/env python3
"""Reopen discovery seen_candidates stuck after LLM infrastructure failures.

Deletes rows where:
  - verdict IN ('llm_error', 'llm_fail'), or
  - status = 'error' (processing/infrastructure failures)

Does NOT touch genuine not-MMIP rejects (verdict='llm') or other terminal rejects.

Dry-run by default. Always writes a full JSON audit of matching rows under
data/backups/ (or --audit-dir) before any delete. On --apply, also copies
discovery.db via sqlite backup unless --no-db-backup.

Prod example:
  docker compose exec scheduler python scripts/reopen_llm_failures.py
  docker compose exec scheduler python scripts/reopen_llm_failures.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RETRYABLE_VERDICTS = ("llm_error", "llm_fail")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _select_stuck(
    conn: sqlite3.Connection,
    *,
    include_error_status: bool,
    errors_only: bool = False,
) -> list[sqlite3.Row]:
    """Return full seen_candidates rows matching reopen criteria."""
    if errors_only:
        sql = """
            SELECT *
            FROM seen_candidates
            WHERE status = 'error'
            ORDER BY status, verdict, url
        """
        return list(conn.execute(sql))

    placeholders = ",".join("?" for _ in RETRYABLE_VERDICTS)
    sql = f"""
        SELECT *
        FROM seen_candidates
        WHERE verdict IN ({placeholders})
    """
    params: list[str] = list(RETRYABLE_VERDICTS)
    if include_error_status:
        sql += " OR status = 'error'"
    sql += " ORDER BY status, verdict, url"
    return list(conn.execute(sql, params))


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def default_audit_dir(db_path: Path) -> Path:
    """Prefer data/backups next to discovery.db; fall back to repo data/backups."""
    sibling = db_path.parent / "backups"
    if sibling.exists() or db_path.parent.name == "data":
        return sibling
    return ROOT / "data" / "backups"


def write_audit_artifact(
    rows: list[sqlite3.Row] | list[dict[str, Any]],
    *,
    audit_dir: Path,
    db_path: Path,
    mode: str,
    include_error_status: bool,
    errors_only: bool,
    limit: int,
) -> Path:
    """Write full matching-row JSON audit; return path. Never deletes."""
    audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    out = audit_dir / f"reopen_llm_failures_{stamp}.json"
    records = [_row_to_dict(r) if isinstance(r, sqlite3.Row) else dict(r) for r in rows]
    by_key: dict[str, int] = {}
    for rec in records:
        key = f"status={rec.get('status')}|verdict={rec.get('verdict') or ''}"
        by_key[key] = by_key.get(key, 0) + 1
    payload = {
        "created_at": _utc_now_iso(),
        "mode": mode,
        "db_path": str(db_path),
        "include_error_status": include_error_status,
        "errors_only": errors_only,
        "limit": limit,
        "matched": len(records),
        "by_status_verdict": by_key,
        "rows": records,
        "urls": [str(rec.get("url") or "") for rec in records],
    }
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out


def backup_discovery_db(db_path: Path, audit_dir: Path) -> Path:
    """Online-safe sqlite backup copy of discovery.db before mutate."""
    audit_dir.mkdir(parents=True, exist_ok=True)
    dest = audit_dir / f"discovery_pre_reopen_{_utc_stamp()}.db"
    # Prefer sqlite Backup API (safe while source may be open); fall back to copy.
    try:
        src = sqlite3.connect(str(db_path))
        try:
            dst = sqlite3.connect(str(dest))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except Exception:
        shutil.copy2(db_path, dest)
    return dest


def reopen_llm_failures(
    *,
    db_path: Path,
    apply: bool = False,
    include_error_status: bool = True,
    errors_only: bool = False,
    limit: int = 0,
    audit_dir: Path | None = None,
    db_backup: bool = True,
    list_all_urls: bool = True,
) -> dict[str, Any]:
    """Select stuck rows, write audit, optionally backup DB and delete.

    Returns a summary dict (matched, deleted, audit_path, db_backup_path, ...).
    """
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")

    out_dir = audit_dir or default_audit_dir(db_path)
    mode = "apply" if apply else "dry-run"

    with _connect(db_path) as conn:
        rows = _select_stuck(
            conn,
            include_error_status=include_error_status,
            errors_only=errors_only,
        )
        if limit and limit > 0:
            rows = rows[:limit]

        by_key: dict[str, int] = {}
        for row in rows:
            key = f"status={row['status']}|verdict={row['verdict'] or ''}"
            by_key[key] = by_key.get(key, 0) + 1

        print(f"[{mode.upper()}] db={db_path}")
        print(f"matched={len(rows)} (include status=error: {include_error_status}; errors_only: {errors_only})")
        for key, count in sorted(by_key.items()):
            print(f"  {key}: {count}")

        if list_all_urls:
            for row in rows:
                print(
                    f"  url: {row['status']:10} {row['verdict'] or '':12} "
                    f"{row['state'] or '':3} {row['url']}"
                )
        else:
            for row in rows[:20]:
                print(
                    f"  sample: {row['status']:10} {row['verdict'] or '':12} "
                    f"{row['state'] or '':3} {row['url']}"
                )
            if len(rows) > 20:
                print(f"  ... and {len(rows) - 20} more (see audit JSON for full list)")

        audit_path = write_audit_artifact(
            rows,
            audit_dir=out_dir,
            db_path=db_path,
            mode=mode,
            include_error_status=include_error_status,
            errors_only=errors_only,
            limit=limit,
        )
        print(f"audit: {audit_path}")

        summary: dict[str, Any] = {
            "mode": mode,
            "matched": len(rows),
            "deleted": 0,
            "audit_path": str(audit_path),
            "db_backup_path": None,
            "by_status_verdict": by_key,
        }

        if not apply:
            print("No changes written. Re-run with --apply to delete these rows.")
            return summary

        if not rows:
            print("Nothing to reopen.")
            return summary

        db_backup_path: Path | None = None
        if db_backup:
            db_backup_path = backup_discovery_db(db_path, out_dir)
            print(f"db_backup: {db_backup_path}")
            summary["db_backup_path"] = str(db_backup_path)

        urls = [row["url"] for row in rows]
        deleted = 0
        for url in urls:
            cur = conn.execute("DELETE FROM seen_candidates WHERE url = ?", (url,))
            deleted += cur.rowcount
        conn.commit()
        summary["deleted"] = deleted
        print(
            f"Deleted {deleted} seen_candidates row(s). "
            "Next discovery run will retry them. Restore from audit JSON / db_backup if needed."
        )
        return summary


def main(argv: list[str] | None = None) -> int:
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
        "--errors-only",
        action="store_true",
        help="Only reopen status=error rows (ignore llm_error/llm_fail verdict filter)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max rows to show/delete (0 = all)",
    )
    parser.add_argument(
        "--audit-dir",
        default="",
        help="Directory for audit JSON / db backup (default: <db-parent>/backups)",
    )
    parser.add_argument(
        "--no-db-backup",
        action="store_true",
        help="Skip sqlite discovery.db backup on --apply (audit JSON still written)",
    )
    parser.add_argument(
        "--sample-only",
        action="store_true",
        help="Print only first 20 URLs to stdout (full list always in audit JSON)",
    )
    args = parser.parse_args(argv)

    if args.errors_only and args.no_error_status:
        print("ERROR: --errors-only and --no-error-status conflict", file=sys.stderr)
        return 2

    db_path = Path(args.db)
    audit_dir = Path(args.audit_dir) if args.audit_dir else None
    try:
        reopen_llm_failures(
            db_path=db_path,
            apply=args.apply,
            include_error_status=not args.no_error_status,
            errors_only=args.errors_only,
            limit=args.limit,
            audit_dir=audit_dir,
            db_backup=not args.no_db_backup,
            list_all_urls=not args.sample_only,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
