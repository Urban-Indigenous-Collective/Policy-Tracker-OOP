#!/usr/bin/env python3
"""Audit missing Last Update / Session on Pending and Main v3.

Compares current Airtable against backup snapshots and classifies gaps as:
  - content_guard cleared (Validation Warnings contain '; cleared')
  - never populated (empty in both backup and current)
  - lost since backup (had value in backup, empty now)

Usage:
  python scripts/audit_metadata_gaps.py
  python scripts/audit_metadata_gaps.py --json-out .probe_tmp/metadata_gaps_audit.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import REVIEW_STATUS_REJECTED

CLEARED_LU = re.compile(r"Last Update .*not grounded.*cleared", re.I)
CLEARED_SE = re.compile(r"Session .*not grounded.*cleared", re.I)

DEFAULT_BACKUPS = {
    "pending_recent": Path("data/backups/pending-eval-expl-pre-fix.json"),
    "pending_pre_clear": Path("data/backups/pending-pre-indigenous-sponsor-backfill.json"),
    "live_recent": Path("data/backups/live-eval-expl-pre-fix.json"),
    "live_pre_clear": Path("data/backups/live-pre-indigenous-sponsor-backfill.json"),
}


def _infer_source(fields: dict) -> str:
    source = str(fields.get("Source") or "").strip()
    if source:
        return source
    url = (
        fields.get("Bill Overview (Link)")
        or fields.get("Bill Overview")
        or fields.get("Bill Text")
        or ""
    ).lower()
    if "legiscan.com" in url:
        return "LegiScan"
    if any(x in url for x in ("whitehouse.gov", "justice.gov", "federalregister.gov")):
        return "Federal Site"
    if ".gov" in url:
        return "State Site"
    return "(unknown)"


def _load_backup(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    records = payload.get("records") if isinstance(payload, dict) else payload
    return {r["id"]: r.get("fields") or {} for r in records}


def audit_table(records, recent_backup: dict, pre_clear_backup: dict, table_name: str) -> dict:
    summary = {
        "table": table_name,
        "total": 0,
        "missing_last_update": 0,
        "missing_session": 0,
        "missing_both": 0,
        "warnings_cleared_last_update": 0,
        "warnings_cleared_session": 0,
        "never_had_last_update": 0,
        "never_had_session": 0,
        "lost_since_recent_last_update": 0,
        "lost_since_recent_session": 0,
        "restorable_from_pre_clear_last_update": 0,
        "restorable_from_pre_clear_session": 0,
        "by_source": defaultdict(lambda: Counter()),
        "federal_sessions_populated": Counter(),
    }

    for rec in records:
        fields = rec.get("fields") or {}
        if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
            continue
        summary["total"] += 1
        rid = rec["id"]
        source = _infer_source(fields)
        lu = str(fields.get("Last Update") or "").strip()
        sess = str(fields.get("Session") or "").strip()
        warnings = str(fields.get("Validation Warnings") or "")
        recent = recent_backup.get(rid, {})
        pre_clear = pre_clear_backup.get(rid, {})
        r_lu = str(recent.get("Last Update") or "").strip()
        r_sess = str(recent.get("Session") or "").strip()
        p_lu = str(pre_clear.get("Last Update") or "").strip()
        p_sess = str(pre_clear.get("Session") or "").strip()

        if not lu:
            summary["missing_last_update"] += 1
            summary["by_source"][source]["missing_last_update"] += 1
        if not sess:
            summary["missing_session"] += 1
            summary["by_source"][source]["missing_session"] += 1
        if not lu and not sess:
            summary["missing_both"] += 1
            summary["by_source"][source]["missing_both"] += 1
        if CLEARED_LU.search(warnings):
            summary["warnings_cleared_last_update"] += 1
            summary["by_source"][source]["warnings_cleared_last_update"] += 1
        if CLEARED_SE.search(warnings):
            summary["warnings_cleared_session"] += 1
            summary["by_source"][source]["warnings_cleared_session"] += 1
        if not lu and not p_lu and not r_lu:
            summary["never_had_last_update"] += 1
        if not sess and not p_sess and not r_sess:
            summary["never_had_session"] += 1
        if not lu and r_lu:
            summary["lost_since_recent_last_update"] += 1
        if not sess and r_sess:
            summary["lost_since_recent_session"] += 1
        if not lu and p_lu:
            summary["restorable_from_pre_clear_last_update"] += 1
            summary["by_source"][source]["restorable_last_update"] += 1
        if not sess and p_sess:
            summary["restorable_from_pre_clear_session"] += 1
            summary["by_source"][source]["restorable_session"] += 1
        if source == "Federal Site" and sess:
            summary["federal_sessions_populated"][sess] += 1

    summary["by_source"] = {k: dict(v) for k, v in summary["by_source"].items()}
    summary["federal_sessions_populated"] = dict(summary["federal_sessions_populated"])
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    client = AirtableClient()
    pending = list(client.pending_table.all())
    live = list(client.live_table.all())

    pending_recent = _load_backup(DEFAULT_BACKUPS["pending_recent"])
    pending_pre = _load_backup(DEFAULT_BACKUPS["pending_pre_clear"])
    live_recent = _load_backup(DEFAULT_BACKUPS["live_recent"])
    live_pre = _load_backup(DEFAULT_BACKUPS["live_pre_clear"])

    report = {
        "pending": audit_table(pending, pending_recent, pending_pre, "Pending"),
        "main_v3": audit_table(live, live_recent, live_pre, "Main v3"),
    }

    for key, summary in report.items():
        print(f"\n=== {summary['table']} ===")
        for field, value in summary.items():
            if field in ("table", "by_source", "federal_sessions_populated"):
                continue
            print(f"{field}={value}")
        print("by_source:")
        for src, counts in sorted(summary["by_source"].items()):
            print(f"  {src}: {counts}")
        if summary["federal_sessions_populated"]:
            print("federal_sessions_populated:")
            for sess, count in sorted(
                summary["federal_sessions_populated"].items(), key=lambda x: -x[1]
            ):
                print(f"  {sess!r}: {count}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
        print(f"\nWrote {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
