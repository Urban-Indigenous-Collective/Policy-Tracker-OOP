#!/usr/bin/env python3
"""Optional weekly LegiScan dataset sync (follow-up / historical backfill).

LegiScan publishes full session JSON dumps each Sunday via getDatasetList/getDataset.
Use this instead of per-bill getBill when backfilling historical sessions.

This script is report-only by default — it lists available datasets without downloading.
Set LEGISCAN_DATASET_DOWNLOAD=true to fetch dataset metadata (requires access_key per dump).

See: https://legiscan.com/datasets
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from api_client import APIClient, LegiScanAPIError, LegiScanOverlimitError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="List or sync LegiScan weekly datasets")
    parser.add_argument(
        "--state",
        default=os.getenv("LEGISCAN_DATASET_STATE", "ALL"),
        help="State code or ALL (default ALL)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Fetch getDataset for each listed session (uses quota; off by default)",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("LEGISCAN_DATASET_INDEX", "data/legiscan_dataset_index.json"),
        help="Write dataset list JSON to this path",
    )
    args = parser.parse_args()

    key = os.getenv("LEGISCAN_KEY")
    if not key:
        logger.error("LEGISCAN_KEY must be set")
        return 1

    download = args.download or os.getenv("LEGISCAN_DATASET_DOWNLOAD", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    api = APIClient(key)
    try:
        listing = api.get_dataset_list(args.state)
    except (LegiScanOverlimitError, LegiScanAPIError) as exc:
        logger.error("getDatasetList failed: %s", exc)
        return 1
    finally:
        api.log_stats()

    if not listing or listing.get("status") != "OK":
        logger.error("Unexpected getDatasetList response: %s", listing)
        return 1

    datasets = (listing.get("datasetlist") or {}).get("dataset") or []
    if isinstance(datasets, dict):
        datasets = list(datasets.values())

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    index = {"state": args.state, "datasets": datasets}
    out_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    logger.info("Wrote %d dataset entries to %s", len(datasets), out_path)

    if download:
        for entry in datasets:
            session_id = entry.get("session_id")
            access_key = entry.get("access_key") or ""
            if not session_id:
                continue
            try:
                api.get_dataset(session_id, access_key=access_key)
            except (LegiScanOverlimitError, LegiScanAPIError) as exc:
                logger.error("getDataset failed session_id=%s: %s", session_id, exc)
                break
        api.log_stats()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
