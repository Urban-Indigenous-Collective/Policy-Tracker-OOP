#!/usr/bin/env python3
"""Manually run the MMIP discovery pipeline."""

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from discovery.pipeline import DiscoveryPipeline
from main_application import MainApplication

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Run MMIP policy discovery pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and gate candidates without writing to Airtable or Slack",
    )
    parser.add_argument(
        "--legiscan-only",
        action="store_true",
        help="Only run LegiScan search (skip state site crawler)",
    )
    args = parser.parse_args()

    legiscan_key = os.getenv("LEGISCAN_KEY")
    if not legiscan_key:
        logger.error("LEGISCAN_KEY must be set")
        sys.exit(1)

    logger.info("Initializing application...")
    app = MainApplication(legiscan_key)

    state_source = None
    if args.legiscan_only:
        from discovery.site_crawler import StateSiteSource

        class _LegiscanOnlyStateSource(StateSiteSource):
            def discover(self):
                return iter([])

        state_source = _LegiscanOnlyStateSource()

    pipeline = DiscoveryPipeline(
        main_app=app,
        dry_run=args.dry_run,
        state_source=state_source,
    )
    stats = pipeline.run()

    logger.info(
        "Run complete: discovered=%d analyzed=%d rejected=%d skipped=%d errors=%d",
        stats.discovered,
        stats.analyzed,
        stats.rejected,
        stats.skipped,
        stats.errors,
    )
    if args.dry_run:
        logger.info("Dry run — no records written to Airtable or Slack")


if __name__ == "__main__":
    main()
