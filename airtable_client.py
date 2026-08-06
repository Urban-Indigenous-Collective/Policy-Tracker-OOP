import logging
import os
from typing import Any, Optional

from pyairtable import Table

from airtable_fields import (
    BILL_FIELD_NAMES,
    BILL_OVERVIEW_FIELD,
    BILL_OVERVIEW_LINK_FIELD,
    LIVE_REVIEW_STATUS_FIELD,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_LIVE,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REJECTED,
    REVIEW_STATUS_SEND_BACK,
)

logger = logging.getLogger(__name__)


def _escape_formula_value(value: str) -> str:
    return str(value).replace("'", "\\'")


class AirtableClient:
    """Read/write client for Main v3 (live) and Pending review tables."""

    def __init__(self):
        api_key = os.getenv("AIRTABLE_API_KEY")
        base_id = os.getenv("AIRTABLE_BASE_ID")
        live_table_name = os.getenv("AIRTABLE_TABLE", "Main v3")
        pending_table_name = os.getenv("AIRTABLE_PENDING_TABLE", "Pending")

        if not api_key or not base_id:
            raise ValueError("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set")

        self.live_table = Table(api_key, base_id, live_table_name)
        self.pending_table = Table(api_key, base_id, pending_table_name)
        self.live_table_name = live_table_name
        self.pending_table_name = pending_table_name

    # --- Legacy duplicate check (Main v3) ---

    def check_url_in_airtable(self, url, category=BILL_OVERVIEW_LINK_FIELD):
        formula = f"{{{category}}} = '{_escape_formula_value(url)}'"
        records = self.live_table.all(formula=formula)
        if records:
            return True, records[0]["fields"]
        return False, None

    def url_exists_anywhere(self, url: str) -> bool:
        """Check Pending and Main v3 for a bill overview URL."""
        escaped = _escape_formula_value(url)
        checks = [
            (self.live_table, BILL_OVERVIEW_LINK_FIELD),
            (self.pending_table, BILL_OVERVIEW_LINK_FIELD),
            (self.live_table, BILL_OVERVIEW_FIELD),
        ]
        for table, field in checks:
            formula = f"{{{field}}} = '{escaped}'"
            try:
                if table.all(formula=formula):
                    return True
            except Exception as exc:
                logger.warning("Airtable lookup failed for field %s: %s", field, exc)
        return False

    def find_by_url(self, table: Table, url: str, field: str = BILL_OVERVIEW_LINK_FIELD) -> Optional[dict]:
        escaped = _escape_formula_value(url)
        formula = f"{{{field}}} = '{escaped}'"
        try:
            records = table.all(formula=formula)
        except Exception as exc:
            logger.warning("Airtable find_by_url failed for field %s: %s", field, exc)
            return None
        return records[0] if records else None

    # --- CRUD ---

    def create_record(self, table: Table, fields: dict[str, Any]) -> dict:
        return table.create(fields)

    def update_record(self, table: Table, record_id: str, fields: dict[str, Any]) -> dict:
        return table.update(record_id, fields)

    def delete_record(self, table: Table, record_id: str) -> None:
        table.delete(record_id)

    def list_by_status(self, table: Table, status_field: str, status_value: str) -> list[dict]:
        formula = f"{{{status_field}}} = '{_escape_formula_value(status_value)}'"
        return table.all(formula=formula)

    # --- Pending workflow helpers ---

    def list_pending_approved(self) -> list[dict]:
        return self.list_by_status(self.pending_table, "Review Status", REVIEW_STATUS_APPROVED)

    def list_pending_rejected(self) -> list[dict]:
        return self.list_by_status(self.pending_table, "Review Status", REVIEW_STATUS_REJECTED)

    def list_pending_for_refresh(self) -> list[dict]:
        """Pending rows eligible for legislative status refresh (excludes Rejected)."""
        records = self.pending_table.all()
        return [
            record
            for record in records
            if (record.get("fields") or {}).get("Review Status") != REVIEW_STATUS_REJECTED
        ]

    def list_live_send_back(self) -> list[dict]:
        return self.list_by_status(self.live_table, LIVE_REVIEW_STATUS_FIELD, REVIEW_STATUS_SEND_BACK)

    def create_pending_record(
        self,
        bill_data: dict[str, Any],
        source: str,
        relevance_confidence: float,
        relevance_rationale: str,
        discovered_on: str,
    ) -> dict:
        fields = {k: bill_data.get(k, "") for k in BILL_FIELD_NAMES}
        fields.update(
            {
                "Review Status": REVIEW_STATUS_PENDING,
                "Source": source,
                "Relevance Confidence": relevance_confidence,
                "Relevance Rationale": relevance_rationale,
                "Discovered On": discovered_on,
            }
        )
        return self.create_record(self.pending_table, fields)

    def create_live_record(self, fields: dict[str, Any]) -> dict:
        live_fields = {k: fields.get(k, "") for k in BILL_FIELD_NAMES if k in fields or fields.get(k)}
        live_fields[LIVE_REVIEW_STATUS_FIELD] = REVIEW_STATUS_LIVE
        return self.create_record(self.live_table, live_fields)

    def pending_record_url(self, record: dict) -> str:
        fields = record.get("fields") or {}
        return fields.get(BILL_OVERVIEW_LINK_FIELD) or fields.get(BILL_OVERVIEW_FIELD) or ""

    def record_to_fields(self, record: dict) -> dict[str, Any]:
        return dict(record.get("fields") or {})

    def all_live_records(self) -> list[dict]:
        return self.live_table.all()
