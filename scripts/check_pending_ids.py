#!/usr/bin/env python3
"""Check Pending record existence and review status."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()
from airtable_client import AirtableClient

ids = sys.argv[1:] or []
client = AirtableClient()
for rid in ids:
    try:
        rec = client.pending_table.get(rid)
        f = rec.get("fields") or {}
        print(
            json.dumps(
                {
                    "id": rid,
                    "status": "exists",
                    "review": f.get("Review Status"),
                    "state": f.get("State"),
                    "bill": f.get("Bill Number"),
                    "name": (f.get("Name") or "")[:70],
                    "discovered_on": f.get("Discovered On"),
                }
            )
        )
    except Exception as e:
        print(json.dumps({"id": rid, "status": "missing_or_deleted", "error": str(e)[:160]}))
