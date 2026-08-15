#!/usr/bin/env python3
"""Mark Pending records as Rejected and suppress their URLs from rediscovery.

Dry-run by default. The next `approval_sync` run deletes rows left in the
Rejected state, so this script also writes a `rejected` verdict to the seen
store keyed on Bill Text — rows discovered from a crawl often have no Bill
Overview (Link), which is the only URL approval_sync suppresses.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, REVIEW_STATUS_REJECTED
from discovery.seen_store import SeenStore

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def _record_url(fields: dict) -> str:
    return fields.get(BILL_OVERVIEW_LINK_FIELD) or fields.get("Bill Text") or ""


def _load_ids(args: argparse.Namespace) -> list[str]:
    ids = list(args.record_ids)
    if args.ids_file:
        ids.extend(
            line.strip()
            for line in Path(args.ids_file).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )
    seen: set[str] = set()
    return [rid for rid in ids if not (rid in seen or seen.add(rid))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record_ids", nargs="*", help="Airtable Pending record ids")
    parser.add_argument("--ids-file", default="", help="File with one record id per line")
    parser.add_argument("--reason", default="junk row: link is not a policy document")
    parser.add_argument("--confirm", action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--no-suppress", action="store_true", help="Skip the seen-store write")
    args = parser.parse_args()

    record_ids = _load_ids(args)
    if not record_ids:
        parser.error("no record ids provided")

    load_dotenv(ROOT / ".env")
    client = AirtableClient()
    store = None if args.no_suppress else SeenStore(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))

    updated = 0
    for record_id in record_ids:
        try:
            record = client.pending_table.get(record_id)
        except Exception as exc:
            logger.error("%s: could not read record (%s)", record_id, exc)
            continue

        fields = record.get("fields") or {}
        url = _record_url(fields)
        label = f"{record_id} [{fields.get('State', '?')}] {fields.get('Name', '?')[:60]}"

        if not args.confirm:
            print(f"DRY RUN would reject {label}\n    {url}")
            continue

        warnings = str(fields.get("Validation Warnings") or "").strip()
        client.update_record(
            client.pending_table,
            record_id,
            {
                "Review Status": REVIEW_STATUS_REJECTED,
                "Validation Warnings": f"{warnings}; {args.reason}".strip("; "),
            },
        )
        if store and url:
            store.upsert(
                url,
                fields.get("Source", "state_site"),
                state=fields.get("State", ""),
                status="rejected",
                verdict=args.reason,
            )
        updated += 1
        print(f"Rejected {label}")

    if args.confirm:
        print(f"\nMarked {updated} / {len(record_ids)} record(s) Rejected in {client.pending_table_name}")
    else:
        print(f"\nDry run: {len(record_ids)} record(s) would be rejected. Re-run with --confirm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
