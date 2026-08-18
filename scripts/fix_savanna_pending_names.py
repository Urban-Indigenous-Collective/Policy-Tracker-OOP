#!/usr/bin/env python3
"""Clarify Savanna's Act Pending records (US HB2733 House vs S.227 Senate)."""
import os, sys
sys.path.insert(0, "/app")
from dotenv import load_dotenv
load_dotenv()
from airtable_client import AirtableClient

FIXES = {
    "reccNAgI2q3a31ril": {
        "Name": "Savanna's Act (HB2733 — House companion, failed)",
        "Bill Number": "HB2733",
    },
    "recFSGtZNbTbM6b0b": {
        "Name": "Savanna's Act (S. 227 — enacted)",
        "Bill Number": "SB227",
    },
}

def main():
    apply = "--apply" in sys.argv
    client = AirtableClient()
    for rid, fields in FIXES.items():
        print(f"{'APPLY' if apply else 'DRY'} {rid}: {fields}")
        if apply:
            client.update_record(client.pending_table, rid, fields)

if __name__ == "__main__":
    main()
