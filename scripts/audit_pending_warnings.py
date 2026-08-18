#!/usr/bin/env python3
"""List Pending rows with Validation Warnings and audit Savanna's Act record."""
import json
import os
import sys

sys.path.insert(0, "/app")
from dotenv import load_dotenv
load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import REVIEW_STATUS_REJECTED
from api_client import APIClient
from legiscan_processor import LegiScanProcessor

air = AirtableClient()
api = APIClient(os.environ["LEGISCAN_KEY"])
leg = LegiScanProcessor(None, api)

warned = []
for rec in air.pending_table.all():
    f = rec.get("fields") or {}
    if f.get("Review Status") == REVIEW_STATUS_REJECTED:
        continue
    w = str(f.get("Validation Warnings") or "").strip()
    if w:
        warned.append({
            "id": rec["id"],
            "name": (f.get("Name") or "")[:70],
            "state": f.get("State"),
            "bill_number": f.get("Bill Number"),
            "review": f.get("Review Status"),
            "source": f.get("Source"),
            "warnings": w,
            "overview": f.get("Bill Overview (Link)") or f.get("Bill Overview") or f.get("Bill Text"),
        })

print("=== PENDING WITH VALIDATION WARNINGS ===")
print(f"count={len(warned)}")
for row in warned:
    print(json.dumps(row, indent=2))
    print("---")

print("=== SAVANNA / HB2733 PENDING ===")
for rec in air.pending_table.all():
    f = rec.get("fields") or {}
    blob = " ".join(str(f.get(k, "") or "") for k in ("Name", "Bill Number", "Bill Text", "Summary")).lower()
    if "savanna" in blob or (f.get("Bill Number") == "HB2733" and f.get("State") in ("US", "National")):
        print(json.dumps({
            "id": rec["id"],
            "name": f.get("Name"),
            "state": f.get("State"),
            "bill_number": f.get("Bill Number"),
            "session": f.get("Session"),
            "status": f.get("Status"),
            "review": f.get("Review Status"),
            "warnings": f.get("Validation Warnings"),
            "overview": f.get("Bill Overview (Link)") or f.get("Bill Overview"),
            "bill_text": f.get("Bill Text"),
            "summary": (f.get("Summary") or "")[:200],
        }, indent=2))
        url = f.get("Bill Text") or f.get("Bill Overview (Link)") or ""
        if url:
            bid = leg.resolve_bill_id(url, state=str(f.get("State") or ""), bill_number=str(f.get("Bill Number") or ""))
            if bid:
                d = api.get_bill_details(bid)
                b = d.get("bill") or {}
                print("legiscan:", json.dumps({
                    "bill_id": bid,
                    "number": b.get("bill_number"),
                    "state": b.get("state"),
                    "title": b.get("title"),
                    "url": leg.get_bill_link(b),
                }, indent=2))
        print("---")

# Real Savanna's Act federal bills
print("=== LEGISCAN SAVANNA'S ACT (federal) ===")
for url in [
    "https://legiscan.com/US/bill/HR2733/2019",
    "https://legiscan.com/US/bill/S227/2019",
    "https://legiscan.com/US/bill/HR4485/2019",
]:
    bid = leg.resolve_bill_id(url)
    if bid:
        d = api.get_bill_details(bid)
        b = d.get("bill") or {}
        print(url, "->", b.get("bill_number"), "|", (b.get("title") or "")[:100])
