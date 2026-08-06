#!/usr/bin/env python3
"""Manually run the legislative status refresh pass for Pending and Live bills."""

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from discovery.status_refresh import build_pipeline
from scripts.live_snapshot import backup_live_table

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Refresh LegiScan status for tracked bills")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and diff without writing to Airtable or Slack",
    )
    args = parser.parse_args()

    if not os.getenv("LEGISCAN_KEY"):
        logger.error("LEGISCAN_KEY must be set")
        sys.exit(1)

    if not args.dry_run:
        try:
            backup_path = backup_live_table()
            logger.info("Live table backup saved to %s", backup_path)
        except Exception as exc:
            logger.exception("Live table backup failed: %s", exc)
            sys.exit(1)

    pipeline = build_pipeline(dry_run=args.dry_run)
    stats = pipeline.run()

    logger.info(
        "Run complete: checked=%d updated=%d unchanged=%d skipped_non_legiscan=%d "
        "resolve_failed=%d getbill_failed=%d identity_mismatch=%d errors=%d",
        stats.checked,
        stats.updated,
        stats.unchanged,
        stats.skipped_non_legiscan,
        stats.resolve_failed,
        stats.getbill_failed,
        stats.identity_mismatch,
        stats.errors,
    )
    if args.dry_run:
        logger.info("Dry run — no records written to Airtable or Slack")


if __name__ == "__main__":
    main()
