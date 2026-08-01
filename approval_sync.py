import logging
import os
from typing import Any

from airtable_client import AirtableClient
from airtable_fields import (
    BILL_FIELD_NAMES,
    BILL_OVERVIEW_FIELD,
    BILL_OVERVIEW_LINK_FIELD,
    LIVE_REVIEW_STATUS_FIELD,
    PENDING_EXTRA_FIELDS,
    REVIEW_STATUS_LIVE,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REJECTED,
)
from discovery.seen_store import SeenStore
from slack_client import SlackNotifier

logger = logging.getLogger(__name__)


class ApprovalSync:
    """Sync approved/rejected records between Pending and Main v3 tables."""

    def __init__(
        self,
        airtable: AirtableClient | None = None,
        seen_store: SeenStore | None = None,
        slack: SlackNotifier | None = None,
    ):
        self.airtable = airtable or AirtableClient()
        self.seen_store = seen_store or SeenStore(
            os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
        )
        self.slack = slack or SlackNotifier()

    def _fields_for_live(self, pending_fields: dict[str, Any]) -> dict[str, Any]:
        live_fields = {k: pending_fields.get(k, "") for k in BILL_FIELD_NAMES}
        live_fields[LIVE_REVIEW_STATUS_FIELD] = REVIEW_STATUS_LIVE
        overview = pending_fields.get(BILL_OVERVIEW_FIELD) or pending_fields.get("Bill Overview (Link)")
        if overview:
            live_fields[BILL_OVERVIEW_LINK_FIELD] = overview
        return live_fields

    def _fields_for_pending(self, live_fields: dict[str, Any]) -> dict[str, Any]:
        pending_fields = {k: live_fields.get(k, "") for k in BILL_FIELD_NAMES}
        overview = live_fields.get(BILL_OVERVIEW_FIELD) or live_fields.get(BILL_OVERVIEW_LINK_FIELD)
        if overview:
            pending_fields[BILL_OVERVIEW_FIELD] = overview
        pending_fields["Review Status"] = REVIEW_STATUS_PENDING
        for extra in PENDING_EXTRA_FIELDS:
            if extra not in pending_fields:
                pending_fields[extra] = live_fields.get(extra, "")
        pending_fields["Source"] = live_fields.get("Source", "Manual")
        return pending_fields

    def _move_to_live(self, record: dict) -> bool:
        record_id = record["id"]
        fields = self.airtable.record_to_fields(record)
        url = self.airtable.pending_record_url(record)

        existing = self.airtable.find_by_url(
            self.airtable.live_table, url, field=BILL_OVERVIEW_LINK_FIELD
        )
        if not existing:
            existing = self.airtable.find_by_url(
                self.airtable.live_table, url, field=BILL_OVERVIEW_FIELD
            )

        if existing:
            logger.info("Record already in live table, deleting pending: %s", url)
            self.airtable.delete_record(self.airtable.pending_table, record_id)
            self.seen_store.update_status(url, "approved")
            return True

        live_fields = self._fields_for_live(fields)
        created = self.airtable.create_live_record(live_fields)
        created_id = created.get("id")
        if not created_id:
            raise RuntimeError(f"Failed to create live record for {url}")

        verify = self.airtable.find_by_url(
            self.airtable.live_table, url, field=BILL_OVERVIEW_LINK_FIELD
        ) or self.airtable.find_by_url(self.airtable.live_table, url, field=BILL_OVERVIEW_FIELD)
        if not verify:
            raise RuntimeError(f"Live record verification failed for {url}")

        self.seen_store.log_move("pending_to_live", url, live_fields)
        self.airtable.delete_record(self.airtable.pending_table, record_id)
        self.seen_store.update_status(url, "approved")

        self.slack.notify_approval(
            fields.get("Title", "Untitled"),
            fields.get("State", ""),
            "to_live",
        )
        logger.info("Moved to live: %s (live_id=%s)", url, created_id)
        return True

    def _move_to_pending(self, record: dict) -> bool:
        record_id = record["id"]
        fields = self.airtable.record_to_fields(record)
        url = fields.get(BILL_OVERVIEW_LINK_FIELD) or fields.get(BILL_OVERVIEW_FIELD) or ""

        existing = self.airtable.find_by_url(self.airtable.pending_table, url)
        if existing:
            logger.info("Record already in pending, deleting live: %s", url)
            self.airtable.delete_record(self.airtable.live_table, record_id)
            self.seen_store.update_status(url, "pending")
            return True

        pending_fields = self._fields_for_pending(fields)
        created = self.airtable.create_record(self.airtable.pending_table, pending_fields)
        created_id = created.get("id")
        if not created_id:
            raise RuntimeError(f"Failed to create pending record for {url}")

        verify = self.airtable.find_by_url(self.airtable.pending_table, url)
        if not verify:
            raise RuntimeError(f"Pending record verification failed for {url}")

        self.seen_store.log_move("live_to_pending", url, pending_fields)
        self.airtable.delete_record(self.airtable.live_table, record_id)
        self.seen_store.update_status(url, "pending")

        self.slack.notify_approval(
            fields.get("Title", "Untitled"),
            fields.get("State", ""),
            "to_pending",
        )
        logger.info("Moved to pending: %s (pending_id=%s)", url, created_id)
        return True

    def _handle_rejected(self, record: dict) -> None:
        record_id = record["id"]
        fields = self.airtable.record_to_fields(record)
        url = self.airtable.pending_record_url(record)
        self.airtable.delete_record(self.airtable.pending_table, record_id)
        if url:
            self.seen_store.update_status(url, "rejected", verdict=REVIEW_STATUS_REJECTED)
        logger.info("Rejected and removed from pending: %s", fields.get("Title", record_id))

    def run(self) -> dict[str, int]:
        stats = {"approved": 0, "send_back": 0, "rejected": 0, "errors": 0}

        for record in self.airtable.list_pending_approved():
            try:
                if self._move_to_live(record):
                    stats["approved"] += 1
            except Exception as exc:
                logger.exception("Error moving to live: %s", exc)
                stats["errors"] += 1
                self.slack.notify_error(f"Approval sync failed (to live): {exc}")

        for record in self.airtable.list_live_send_back():
            try:
                if self._move_to_pending(record):
                    stats["send_back"] += 1
            except Exception as exc:
                logger.exception("Error moving to pending: %s", exc)
                stats["errors"] += 1
                self.slack.notify_error(f"Approval sync failed (to pending): {exc}")

        for record in self.airtable.list_pending_rejected():
            try:
                self._handle_rejected(record)
                stats["rejected"] += 1
            except Exception as exc:
                logger.exception("Error handling rejection: %s", exc)
                stats["errors"] += 1

        logger.info("Approval sync complete: %s", stats)
        return stats


if __name__ == "__main__":
    import logging
    import os

    from dotenv import load_dotenv

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    load_dotenv()
    sync = ApprovalSync()
    sync.run()
