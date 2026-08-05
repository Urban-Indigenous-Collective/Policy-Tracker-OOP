#!/usr/bin/env python3
"""Apply Bill Overview (Link) to legacy Live rows missing canonical URLs."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD

# Researched canonical URLs (subagent b0730931)
UPDATES = [
    (
        "rechr9e0aMN9Y53fJ",
        "https://www.congress.gov/bill/117th-congress/house-bill/1620",
    ),
    (
        "recR9GCIsAv873ey0",
        "https://governor.nc.gov/documents/files/governor-proclaims-day-awareness-missing-and-murdered-indigenous-women-2020/open",
    ),
    (
        "recQjSO7BGbNiDWIr",
        "https://www.governor.nd.gov/sites/www/files/documents/proclamations/MMIW%20Awareness%20Day%202022.pdf",
    ),
    (
        "reck2oh3mEjLZir8m",
        "https://www.federalregister.gov/documents/2021/11/18/2021-25287/improving-public-safety-and-criminal-justice-for-native-americans-and-addressing-the-crisis-of",
    ),
]


def main() -> None:
    dry_run = "--apply" not in sys.argv
    client = AirtableClient()

    for rec_id, url in UPDATES:
        before = client.live_table.get(rec_id)
        fields = before.get("fields") or {}
        name = fields.get("Name", "")
        before_url = fields.get(BILL_OVERVIEW_LINK_FIELD, "")
        print(f"{rec_id} ({name})")
        print(f"  before: {before_url!r}")
        print(f"  target: {url!r}")
        if not dry_run:
            client.update_record(client.live_table, rec_id, {BILL_OVERVIEW_LINK_FIELD: url})
            after = client.live_table.get(rec_id)
            after_url = (after.get("fields") or {}).get(BILL_OVERVIEW_LINK_FIELD, "")
            status = "OK" if after_url == url else f"MISMATCH ({after_url!r})"
            print(f"  after:  {after_url!r} [{status}]")
        print()

    if dry_run:
        print("Dry run — pass --apply to update Airtable.")
        sys.exit(0)


if __name__ == "__main__":
    main()
