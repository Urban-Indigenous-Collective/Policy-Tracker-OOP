#!/usr/bin/env python3
"""Rewrite USAO district (or state governor) Session values to presidential administration.

Federal Site rows should use the administration in office at publication
(e.g. Biden Administration), not USAO district names or governor terms.

Usage:
  python scripts/fix_usao_session_semantics.py
  python scripts/fix_usao_session_semantics.py --apply
  python scripts/fix_usao_session_semantics.py --record-id rec7itTIJW4JAIaul --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, REVIEW_STATUS_REJECTED
from scripts.backfill_metadata import administration_from_date, _infer_source

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

USAO_SESSION_RE = re.compile(
    r"(District of|Western District|Eastern District|Northern District|Southern District|"
    r"Middle District|U\.S\. Attorney|USAO|Attorney's Office)",
    re.I,
)
ADMIN_SESSION_RE = re.compile(r"(Obama|Trump|Biden|Biden-Harris) Administration$", re.I)
GOVERNOR_SESSION_RE = re.compile(r"Administration$", re.I)

# Known bad rows from metadata audit (d24a42dd).
DEFAULT_RECORD_IDS = [
    "rec7itTIJW4JAIaul",
    "recESLgY0wT1DgnG9",
    "recLbfCl8wgij4gJf",
    "recF6DPveww41Xsqa",
    "recwMSv5kNMvaqfQY",
    "reczBpE8z1uPv4MoI",
    "recvOBM4uJ2CbTij3",
    "recLIVZK1gMfJb3rv",
]


def _record_url(fields: dict) -> str:
    return (
        fields.get(BILL_OVERVIEW_LINK_FIELD)
        or fields.get("Bill Overview")
        or fields.get("Bill Text")
        or ""
    )


def _needs_usao_session_fix(fields: dict, record_id: str, explicit_ids: set[str]) -> bool:
    if record_id in explicit_ids:
        return True
    if _infer_source(fields, _record_url(fields)) != "Federal Site":
        return False
    session = str(fields.get("Session") or "").strip()
    if not session or ADMIN_SESSION_RE.search(session):
        return False
    url = _record_url(fields).lower()
    if "justice.gov" in url and GOVERNOR_SESSION_RE.search(session):
        return True
    return bool(USAO_SESSION_RE.search(session))


def _target_administration(fields: dict) -> str:
    date_val = str(fields.get("Last Update") or "").strip()
    return administration_from_date(date_val)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--record-id", action="append", default=[])
    parser.add_argument("--scan-all", action="store_true", help="Fix all matching Pending rows, not just defaults")
    args = parser.parse_args()

    explicit_ids = set(args.record_id or DEFAULT_RECORD_IDS)
    client = AirtableClient()

    would_fix = 0
    applied = 0

    for record in client.pending_table.all():
        fields = record.get("fields") or {}
        rid = record["id"]
        if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
            continue
        if not args.scan_all and rid not in explicit_ids:
            continue
        if not _needs_usao_session_fix(fields, rid, explicit_ids):
            continue

        current = str(fields.get("Session") or "").strip()
        target = _target_administration(fields)
        if not target:
            logger.warning("%s: no administration for LU=%r; skip", rid, fields.get("Last Update"))
            continue
        if current == target:
            logger.info("%s: already %r", rid, target)
            continue

        would_fix += 1
        logger.info(
            "%s %s: Session %r -> %r (LU=%r)",
            "APPLY" if args.apply else "DRY-RUN",
            rid,
            current,
            target,
            fields.get("Last Update"),
        )
        if args.apply:
            client.update_record(client.pending_table, rid, {"Session": target})
            applied += 1
            time.sleep(0.25)

    print(f"would_fix={would_fix} applied={applied} apply={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
