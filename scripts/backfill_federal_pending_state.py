#!/usr/bin/env python3
"""Report (and optionally fix) Pending rows with wrong National state for USAO/DOJ items.

Safe by default: ``--dry-run`` lists candidates; pass ``--apply`` to patch State in Airtable.
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
from discovery.federal_jurisdiction import infer_federal_jurisdiction

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def _overview_url(fields: dict) -> str:
    return str(
        fields.get("Bill Overview (Link)")
        or fields.get("Bill Overview")
        or fields.get("Bill Text")
        or ""
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update Airtable Pending rows (default is dry-run report only)",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    client = AirtableClient()
    records = client.pending_table.all()

    candidates: list[dict] = []
    for record in records:
        fields = record.get("fields") or {}
        if (fields.get("Source") or "") != "Federal Site":
            continue
        state = str(fields.get("State") or "").strip()
        if state and state.lower() not in {"national", "federal"}:
            continue
        url = _overview_url(fields)
        if not url or "justice.gov" not in url.lower():
            continue
        inferred = infer_federal_jurisdiction(
            url,
            title=str(fields.get("Name") or ""),
            body=str(fields.get("Summary") or ""),
        )
        if inferred == "National":
            continue
        candidates.append(
            {
                "id": record["id"],
                "name": fields.get("Name", "")[:80],
                "url": url,
                "current_state": state or "National",
                "inferred_state": inferred,
            }
        )

    print(f"Found {len(candidates)} Pending Federal Site row(s) with State=National but USAO/state signal.")
    for row in candidates[:50]:
        print(
            f"  {row['id']}  {row['current_state']} -> {row['inferred_state']}  "
            f"{row['name']!r}  {row['url']}"
        )
    if len(candidates) > 50:
        print(f"  ... and {len(candidates) - 50} more")

    if not args.apply:
        if candidates:
            print("\nRe-run with --apply to patch State on the rows above.")
        return 0

    updated = 0
    for row in candidates:
        client.pending_table.update(row["id"], {"State": row["inferred_state"]})
        updated += 1
        logger.info("Updated %s -> State=%s", row["id"], row["inferred_state"])

    print(f"Updated {updated} Pending row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
