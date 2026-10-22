"""Filter Main v3 rows eligible for the public site."""

from __future__ import annotations

import logging
import os
from typing import Any

from airtable_fields import LIVE_REVIEW_STATUS_FIELD, REVIEW_STATUS_LIVE

logger = logging.getLogger(__name__)


def require_live_review_status() -> bool:
    return os.getenv("PUBLIC_API_REQUIRE_LIVE", "1").lower() in ("1", "true", "yes")


def strict_review_status_only() -> bool:
    """When set, only explicit Review Status = Live (empty Main v3 rows are hidden)."""
    return os.getenv("PUBLIC_API_STRICT_REVIEW_STATUS", "0").lower() in (
        "1",
        "true",
        "yes",
    )


def is_public_live_record(record: dict[str, Any]) -> bool:
    fields = record.get("fields") or {}
    if not require_live_review_status():
        logger.warning(
            "PUBLIC_API_REQUIRE_LIVE is disabled — exposing non-Live Main v3 rows"
        )
        return True
    status = str(fields.get(LIVE_REVIEW_STATUS_FIELD) or "").strip()
    if status == REVIEW_STATUS_LIVE:
        return True
    # Pre-backfill Main v3: legislative rows with no workflow status yet.
    if status == "" and not strict_review_status_only():
        return True
    return False


def filter_public_live_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if is_public_live_record(record)]
