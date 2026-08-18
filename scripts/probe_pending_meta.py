#!/usr/bin/env python3
"""Fetch Pending record metadata for investigation."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from airtable_client import AirtableClient

ids = sys.argv[1:] or ["recGHwmaGfyVkk9mg", "recQuPGGvq3c4QDl2"]
client = AirtableClient()
for rid in ids:
    f = client.pending_table.get(rid)["fields"]
    out = {k: f.get(k) for k in sorted(f) if k in (
        "Name", "State", "Bill Number", "Source", "Review Status", "Categories",
        "Relevance Confidence", "Relevance Rationale", "Discovered On", "Session",
        "Summary", "Bill Overview (Link)", "Bill Text", "Validation Warnings",
    )}
    if out.get("Summary"):
        out["Summary"] = str(out["Summary"])[:300]
    print(json.dumps({"id": rid, **out}, indent=2))
