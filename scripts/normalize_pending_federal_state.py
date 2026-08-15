#!/usr/bin/env python3
"""Normalize Pending federal rows: State=US -> National.

Federal LegiScan bills use API state code US; Airtable convention is National
(see discovery/federal_schema.FEDERAL_STATE).

Usage:
  python scripts/normalize_pending_federal_state.py           # dry-run
  python scripts/normalize_pending_federal_state.py --apply  # write to Airtable
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, BILL_TEXT_FIELD, REVIEW_STATUS_REJECTED
from discovery.federal_schema import FEDERAL_STATE

_FEDERAL_STATE_VALUES = frozenset({"us", "u.s.", "federal", ""})
_FEDERAL_LEGISCAN_RE = re.compile(r"legiscan\.com/US/", re.IGNORECASE)


def _record_url(fields: dict) -> str:
    return (
        fields.get(BILL_OVERVIEW_LINK_FIELD)
        or fields.get("Bill Overview")
        or fields.get(BILL_TEXT_FIELD)
        or ""
    )


def is_federal_pending(fields: dict) -> bool:
    state = str(fields.get("State") or "").strip()
    if state.lower() not in _FEDERAL_STATE_VALUES:
        return False

    url = _record_url(fields)
    source = str(fields.get("Source") or "").strip().lower()
    if _FEDERAL_LEGISCAN_RE.search(url):
        return True
    if source == "legiscan" and state.lower() in _FEDERAL_STATE_VALUES:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write updates to Airtable")
    args = parser.parse_args()

    client = AirtableClient()
    targets: list[tuple[str, dict]] = []

    for record in client.pending_table.all():
        fields = record.get("fields") or {}
        if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
            continue
        if is_federal_pending(fields):
            targets.append((record["id"], fields))

    print(f"found={len(targets)} apply={args.apply}")
    for rid, fields in targets:
        print(
            f"  {rid} | {fields.get('Bill Number')} | "
            f"State={fields.get('State')!r} -> {FEDERAL_STATE!r} | "
            f"{_record_url(fields)[:80]}"
        )
        if args.apply:
            client.update_record(client.pending_table, rid, {"State": FEDERAL_STATE})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
