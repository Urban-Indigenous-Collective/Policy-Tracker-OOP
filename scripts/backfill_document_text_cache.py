#!/usr/bin/env python3
"""Populate document_text.db from Pending Airtable URLs (non-rejected)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from airtable_client import AirtableClient
from airtable_fields import (
    BILL_OVERVIEW_LINK_FIELD,
    BILL_TEXT_FIELD,
    REVIEW_STATUS_REJECTED,
)
from api_client import APIClient
from bill_processor import BillProcessor
from document_processor import DocumentProcessor
from document_text_store import get_document_text_store
from indigenous_database import IndigenousDatabase
from llm.factory import get_llm_provider

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def _record_url(fields: dict) -> str:
    return (
        fields.get(BILL_OVERVIEW_LINK_FIELD)
        or fields.get("Bill Overview")
        or fields.get(BILL_TEXT_FIELD)
        or ""
    ).strip()


def _eligible_pending_records(client: AirtableClient) -> list[dict]:
    records = client.pending_table.all()
    out: list[dict] = []
    for record in records:
        fields = record.get("fields") or {}
        if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
            continue
        if not _record_url(fields):
            continue
        out.append(record)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Max records to process (0 = all)")
    parser.add_argument("--sleep", type=float, default=0.25, help="Pause between fetches")
    parser.add_argument(
        "--record-id",
        action="append",
        default=[],
        help="Process specific Pending record id(s) only",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    store = get_document_text_store()
    if not store:
        logger.error(
            "Document text cache disabled (set DOCUMENT_TEXT_CACHE_ENABLED=true)"
        )
        return 1

    api = APIClient(os.environ["LEGISCAN_KEY"])
    llm = get_llm_provider()
    processor = BillProcessor(
        api,
        llm,
        DocumentProcessor(llm),
        IndigenousDatabase(),
    )
    client = AirtableClient()

    if args.record_id:
        records = [client.pending_table.get(rid) for rid in args.record_id]
    else:
        records = _eligible_pending_records(client)

    if args.limit:
        records = records[: args.limit]

    total = len(records)
    logger.info("Backfilling document text cache for %d Pending record(s)", total)

    ok_count = 0
    fail_count = 0
    skip_count = 0
    failures: list[dict] = []

    for i, record in enumerate(records, start=1):
        rid = record["id"]
        fields = record.get("fields") or {}
        url = _record_url(fields)
        name = fields.get("Name") or fields.get("Title") or rid

        if not url:
            skip_count += 1
            continue

        logger.info("[%d/%d] %s — %s", i, total, rid, url[:100])
        try:
            ok, msg = processor.get_doc_text(url, refresh=True)
        except Exception as exc:
            ok, msg = False, str(exc)
            logger.exception("Fetch failed for %s", rid)

        if ok:
            ok_count += 1
            cached = store.get(url)
            chars = (cached or {}).get("char_len") or len(
                processor.compiled_bill.get("decoded_text") or ""
            )
            logger.info("  cached ok (%s chars)", chars)
        else:
            fail_count += 1
            failures.append({"record_id": rid, "url": url, "name": name, "error": msg})
            logger.warning("  failed: %s", msg)

        if args.sleep:
            time.sleep(args.sleep)

    logger.info(
        "Done: ok=%d fail=%d skip=%d total=%d",
        ok_count,
        fail_count,
        skip_count,
        total,
    )
    if failures:
        for item in failures[:20]:
            logger.info("  failure %s: %s", item["record_id"], item["error"][:200])
        if len(failures) > 20:
            logger.info("  ... and %d more failures", len(failures) - 20)

    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
