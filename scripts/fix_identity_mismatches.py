#!/usr/bin/env python3
"""Proposed fixes for bill identity mismatches — dry-run by default.

Federal LegiScan rows keep State=National (see discovery/federal_schema.FEDERAL_STATE).
LegiScan API uses state code US; that is not written to Airtable.

Usage:
  python scripts/fix_identity_mismatches.py           # print proposal
  python scripts/fix_identity_mismatches.py --apply   # write to Airtable (after approval)
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, BILL_TEXT_FIELD
from api_client import APIClient
from legiscan_processor import LegiScanProcessor

PROPOSED = [
    {
        "record_id": "reclEifxdCtnrvGjY",
        "table": "live",
        "summary": "MN SF36 — wrong overview pointed at SF3663 (voter ID bill). Correct bill is SF36/2023 MMIP reward fund.",
        "legiscan_url": "https://legiscan.com/MN/bill/SF36/2023",
        "extra_fields": {
            "Bill Number": "SF36",
            "State": "MN",
            BILL_TEXT_FIELD: "https://legiscan.com/MN/bill/SF36/2023",
        },
    },
    {
        "record_id": "recvUomhVG2nvk9dy",
        "table": "live",
        "summary": "MN HF3055 — bill number typo (HB3055 → HF3055). LegiScan URL already correct.",
        "legiscan_url": "https://legiscan.com/MN/bill/HF3055/2021",
        "extra_fields": {
            "Bill Number": "HF3055",
            "State": "MN",
        },
    },
    {
        "record_id": "recxhO4O1YIzlCHhG",
        "table": "live",
        "summary": "NY S06924 — bill number formatting (SB6924 → S06924). LegiScan URL already correct.",
        "legiscan_url": "https://legiscan.com/NY/bill/S06924/2021",
        "extra_fields": {
            "Bill Number": "S06924",
            "State": "NY",
        },
    },
]


def legiscan_sync_fields(api: APIClient, legiscan: LegiScanProcessor, url: str) -> dict:
    bill_id = legiscan.resolve_bill_id(url)
    if not bill_id:
        raise RuntimeError(f"Could not resolve {url}")
    details = api.get_bill_details(bill_id)
    bill = details.get("bill") or {}
    fields = legiscan.extract_status_fields(details)
    session = bill.get("session") or {}
    if isinstance(session, dict) and session.get("session_title"):
        fields["Session"] = session["session_title"]
    fields[BILL_OVERVIEW_LINK_FIELD] = legiscan.get_bill_link(bill)
    return fields


def main() -> None:
    apply = "--apply" in sys.argv
    client = AirtableClient()
    api = APIClient(os.environ["LEGISCAN_KEY"])
    legiscan = LegiScanProcessor(indigenous_db=None, api_client=api)

    proposal: list[dict] = []

    for fix in PROPOSED:
        updates = legiscan_sync_fields(api, legiscan, fix["legiscan_url"])
        updates.update(fix.get("extra_fields") or {})
        entry = {
            "record_id": fix["record_id"],
            "summary": fix["summary"],
            "fields": updates,
        }
        proposal.append(entry)
        print(f"{'APPLY' if apply else 'PROPOSED'} {fix['record_id']}: {fix['summary']}")
        print(json.dumps(updates, indent=2))
        print("---")
        if apply:
            client.update_record(client.live_table, fix["record_id"], updates)

    if not apply:
        print(f"\n{len(proposal)} record(s) ready. Run with --apply after approval.")


if __name__ == "__main__":
    main()
