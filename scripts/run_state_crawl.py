#!/usr/bin/env python3
"""Dry-run state site crawler for one state or source."""

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from discovery.site_crawler import StateSiteSource

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Run state site crawler only")
    parser.add_argument("--state", help="Two-letter state code filter, e.g. NC")
    parser.add_argument("--source-id", help="Filter to one source_id from manifest")
    parser.add_argument(
        "--include-review",
        action="store_true",
        help="Include sources still marked review_needed=true",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias for default behavior (crawl only, no Airtable writes)",
    )
    parser.add_argument("--verbose", action="store_true", help="Log each candidate URL")
    parser.add_argument(
        "--sources",
        default=str(ROOT / "sources" / "state_sources.json"),
        help="Path to state_sources.json",
    )
    args = parser.parse_args()

    crawler = StateSiteSource(
        sources_path=args.sources,
        state_filter=args.state,
        source_id_filter=args.source_id,
        include_review_needed=args.include_review,
    )
    count = 0
    for candidate in crawler.discover():
        count += 1
        if args.verbose:
            logger.info(
                "candidate state=%s url=%s title=%s",
                candidate.state,
                candidate.url,
                candidate.title[:80],
            )
    logger.info("State crawl complete: %d candidate link(s)", count)


if __name__ == "__main__":
    main()
