#!/usr/bin/env python3
"""Fix Ida's Law Airtable records and related data quality issues."""
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

# LegiScan ground truth (verified 2026-08-03)
FIXES = [
    {
        "record_id": "rec2exlbYQK8pqqPV",
        "table": "live",
        "reason": "HB2733 House companion failed in committee; was wrongly Status=Passed",
        "fields": {
            "Name": "Ida's Law (HB2733 — House companion, failed in committee)",
            "Bill Number": "HB2733",
            "State": "OK",
            "Session": "2021 Regular Session",
            BILL_OVERVIEW_LINK_FIELD: "https://legiscan.com/OK/bill/HB2733/2021",
            BILL_TEXT_FIELD: "https://legiscan.com/OK/bill/HB2733/2021",
            "Status": "Failed",
            "Progression": "Introduced",
            "Chamber": "House",
            "Chamber Details": "2021-02-25 - H: CR; Do Pass Criminal Justice and Corrections Committee",
            "Last Update": "2021-02-01",
        },
    },
    {
        "record_id": "rec5nk2Egp6IbJV5r",
        "table": "live",
        "reason": "SB172 is the enacted Ida's Law; add LegiScan link and fix Bill Text URL",
        "fields": {
            "Name": "Ida's Law (SB172 — enacted)",
            "Bill Number": "SB172",
            "State": "OK",
            "Session": "2021 Regular Session",
            BILL_OVERVIEW_LINK_FIELD: "https://legiscan.com/OK/bill/SB172/2021",
            BILL_TEXT_FIELD: "https://legiscan.com/OK/bill/SB172/2021",
            "Status": "Passed",
            "Progression": "Passed",
            "Chamber": "Senate",
            "Chamber Details": "2021-04-20 - S: Approved by Governor 04/20/2021",
            "Last Update": "2021-04-20",
        },
    },
    {
        "record_id": "rec6ljJpxd836NDtX",
        "table": "live",
        "reason": "SB230 2022 session — failed Senate bill, clarify name",
        "fields": {
            "Name": "Ida's Law attempt (SB230 — 2022 session, failed)",
            "Session": "2022 Regular Session",
            BILL_OVERVIEW_LINK_FIELD: "https://legiscan.com/OK/bill/SB230/2022",
            BILL_TEXT_FIELD: "https://legiscan.com/OK/bill/SB230/2022",
        },
    },
    {
        "record_id": "recIEgWnaOnod2m3q",
        "table": "live",
        "reason": "SB230 2021 session — failed Senate bill, clarify name",
        "fields": {
            "Name": "Ida's Law attempt (SB230 — 2021 session, failed)",
            "Session": "2021 Regular Session",
            BILL_OVERVIEW_LINK_FIELD: "https://legiscan.com/OK/bill/SB230/2021",
            BILL_TEXT_FIELD: "https://legiscan.com/OK/text/SB230/id/2226402",
        },
    },
]


def verify_fix(api: APIClient, legiscan: LegiScanProcessor, fix: dict) -> None:
    url = fix["fields"][BILL_OVERVIEW_LINK_FIELD]
    bill_id = legiscan.resolve_bill_id(url)
    if not bill_id:
        raise RuntimeError(f"Could not verify LegiScan URL: {url}")
    details = api.get_bill_details(bill_id)
    fresh = legiscan.extract_status_fields(details)
    for key in ("Status", "Progression", "Chamber", "Chamber Details", "Last Update"):
        expected = fix["fields"].get(key)
        if expected and str(fresh.get(key, "")) != str(expected):
            raise RuntimeError(
                f"LegiScan mismatch for {fix['record_id']} field {key}: "
                f"expected {expected!r} got {fresh.get(key)!r}"
            )


def main() -> None:
    dry_run = "--apply" not in sys.argv
    client = AirtableClient()
    api = APIClient(os.environ["LEGISCAN_KEY"])
    legiscan = LegiScanProcessor(indigenous_db=None, api_client=api)

    for fix in FIXES:
        verify_fix(api, legiscan, fix)
        table = client.live_table if fix["table"] == "live" else client.pending_table
        print(f"{'APPLY' if not dry_run else 'DRY-RUN'} {fix['record_id']}: {fix['reason']}")
        if not dry_run:
            client.update_record(table, fix["record_id"], fix["fields"])
        else:
            print(json.dumps(fix["fields"], indent=2))


if __name__ == "__main__":
    main()
