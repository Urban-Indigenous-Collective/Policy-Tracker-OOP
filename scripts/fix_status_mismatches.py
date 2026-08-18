#!/usr/bin/env python3
"""Sync remaining Live records where LegiScan ground truth is clear."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD
from api_client import APIClient
from legiscan_processor import LegiScanProcessor

FIXES = [
    {
        "record_id": "recy1Nzj1YUrKkySI",
        "url": "https://legiscan.com/NM/bill/HB208/2021",
        "overview": "https://legiscan.com/NM/bill/HB208/2021",
        "note": "NM HB208 MMIP task force extension — failed/stalled 2021 session",
    },
    {
        "record_id": "rechbEb41DLbrypAf",
        "url": "https://legiscan.com/NM/bill/SM18/2022",
        "overview": "https://legiscan.com/NM/bill/SM18/2022",
        "note": "NM SM18 memorial — adopted/signed Feb 2022",
    },
]


def legiscan_fields(api: APIClient, legiscan: LegiScanProcessor, url: str) -> dict:
    bill_id = legiscan.resolve_bill_id(url)
    if not bill_id:
        raise RuntimeError(f"unresolved: {url}")
    details = api.get_bill_details(bill_id)
    fields = legiscan.extract_status_fields(details)
    fields[BILL_OVERVIEW_LINK_FIELD] = legiscan.get_bill_link(details.get("bill") or {})
    bill = details.get("bill") or {}
    session = bill.get("session") or {}
    if isinstance(session, dict) and session.get("session_title"):
        fields["Session"] = session["session_title"]
    return fields


def main() -> None:
    apply = "--apply" in sys.argv
    client = AirtableClient()
    api = APIClient(os.environ["LEGISCAN_KEY"])
    legiscan = LegiScanProcessor(indigenous_db=None, api_client=api)

    # Add HB1177 from live search
    for rec in client.all_live_records():
        f = rec.get("fields") or {}
        if str(f.get("Bill Number") or "") == "HB1177" and str(f.get("State") or "") == "WA":
            FIXES.append(
                {
                    "record_id": rec["id"],
                    "url": "https://legiscan.com/WA/bill/HB1177/2023",
                    "overview": "https://legiscan.com/WA/bill/HB1177/2023",
                    "note": "WA HB1177 MMIP — chaptered/effective 2023",
                }
            )
            break

    for fix in FIXES:
        updates = legiscan_fields(api, legiscan, fix["url"])
        if fix.get("overview"):
            updates[BILL_OVERVIEW_LINK_FIELD] = fix["overview"]
        print(f"{'APPLY' if apply else 'DRY-RUN'} {fix['record_id']}: {fix['note']}")
        print(json.dumps(updates, indent=2))
        if apply:
            client.update_record(client.live_table, fix["record_id"], updates)


if __name__ == "__main__":
    main()
