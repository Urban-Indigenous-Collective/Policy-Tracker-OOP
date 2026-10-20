import logging
import os
from pathlib import Path
from typing import Any

from filelock import FileLock

from airtable_client import AirtableClient, is_airtable_rate_limit_error
from airtable_fields import (
    BILL_OVERVIEW_FIELD,
    BILL_OVERVIEW_LINK_FIELD,
    LIVE_REVIEW_STATUS_FIELD,
    REVIEW_STATUS_LIVE,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REJECTED,
)
from airtable_schema import (
    BILL_FIELD_NAMES as LIVE_BILL_FIELD_NAMES,
    DISCOVERY_METADATA_FIELD_NAMES,
    LEGACY_FIELD_RENAMES,
    PENDING_ONLY_FIELD_NAMES,
    SOURCE_CHOICES,
)
from discovery.seen_store import SeenStore
from slack_client import SlackNotifier

logger = logging.getLogger(__name__)

# Pending discovery output still uses Title / Bill Overview / Sponsors; Main v3 uses Name etc.
_LIVE_WRITABLE_FIELDS = frozenset(LIVE_BILL_FIELD_NAMES + DISCOVERY_METADATA_FIELD_NAMES)
_PENDING_WRITABLE_FIELDS = frozenset(
    LIVE_BILL_FIELD_NAMES
    + PENDING_ONLY_FIELD_NAMES
    + DISCOVERY_METADATA_FIELD_NAMES
)
_SKIP_LIVE_FIELDS = frozenset({"Created By", LIVE_REVIEW_STATUS_FIELD})
_PENDING_ONLY_ON_LIVE = frozenset({"Source", "Discovered On"})


def _apply_legacy_renames(fields: dict[str, Any]) -> dict[str, Any]:
    """Map Pending legacy names onto Main v3 / schema-canonical names."""
    working = dict(fields)
    for legacy, canonical in LEGACY_FIELD_RENAMES.items():
        if legacy in working and (canonical not in working or working.get(canonical) in (None, "")):
            working[canonical] = working[legacy]
        working.pop(legacy, None)
    overview = working.get(BILL_OVERVIEW_LINK_FIELD) or working.get(BILL_OVERVIEW_FIELD)
    if overview:
        working[BILL_OVERVIEW_LINK_FIELD] = overview
    working.pop(BILL_OVERVIEW_FIELD, None)
    return working


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
        self.verify_writes = os.getenv("APPROVAL_SYNC_VERIFY_WRITES", "true").lower() in (
            "1",
            "true",
            "yes",
        )

    def _fields_for_live(self, pending_fields: dict[str, Any]) -> dict[str, Any]:
        """Map Pending columns onto Main v3 names (Title→Name, etc.)."""
        working = _apply_legacy_renames(pending_fields)
        live_fields = {
            key: working[key]
            for key in _LIVE_WRITABLE_FIELDS
            if key in working and working[key] not in (None, "")
        }
        live_fields[LIVE_REVIEW_STATUS_FIELD] = REVIEW_STATUS_LIVE
        return live_fields

    def _fields_for_pending(self, live_fields: dict[str, Any]) -> dict[str, Any]:
        """Map a Live row onto Pending-writable columns only."""
        working = {
            key: value
            for key, value in live_fields.items()
            if key not in _SKIP_LIVE_FIELDS
        }
        working = _apply_legacy_renames(working)

        pending_fields = {
            key: working[key]
            for key in _PENDING_WRITABLE_FIELDS
            if key in working and working[key] not in (None, "")
        }
        # Preserve empty-string Validation Warnings only if present on live.
        if "Validation Warnings" in working:
            pending_fields["Validation Warnings"] = working.get("Validation Warnings") or ""

        pending_fields["Review Status"] = REVIEW_STATUS_PENDING
        source = working.get("Source") or ""
        if source not in SOURCE_CHOICES:
            overview_url = str(pending_fields.get(BILL_OVERVIEW_LINK_FIELD) or "")
            if "legiscan.com" in overview_url.lower():
                source = "LegiScan"
            elif any(
                token in overview_url.lower()
                for token in ("justice.gov", "federalregister.gov", "whitehouse.gov")
            ):
                source = "Federal Site"
            else:
                source = "State Site"
        pending_fields["Source"] = source
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

        if self.verify_writes:
            verify = self.airtable.find_by_url(
                self.airtable.live_table, url, field=BILL_OVERVIEW_LINK_FIELD
            ) or self.airtable.find_by_url(self.airtable.live_table, url, field=BILL_OVERVIEW_FIELD)
            if not verify:
                raise RuntimeError(f"Live record verification failed for {url}")

        self.seen_store.log_move("pending_to_live", url, live_fields)
        self.airtable.delete_record(self.airtable.pending_table, record_id)
        self.seen_store.update_status(url, "approved")

        self.slack.notify_approval(
            fields.get("Title") or fields.get("Name") or "Untitled",
            fields.get("State", ""),
            "to_live",
        )
        logger.info("Moved to live: %s (live_id=%s)", url, created_id)
        return True

    def _move_to_pending(self, record: dict) -> bool:
        record_id = record["id"]
        fields = self.airtable.record_to_fields(record)
        url = fields.get(BILL_OVERVIEW_LINK_FIELD) or fields.get(BILL_OVERVIEW_FIELD) or ""

        existing = self.airtable.find_by_url(
            self.airtable.pending_table, url, field=BILL_OVERVIEW_LINK_FIELD
        )
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

        if self.verify_writes:
            verify = self.airtable.find_by_url(
                self.airtable.pending_table, url, field=BILL_OVERVIEW_LINK_FIELD
            )
            if not verify:
                raise RuntimeError(f"Pending record verification failed for {url}")

        self.seen_store.log_move("live_to_pending", url, pending_fields)
        self.airtable.delete_record(self.airtable.live_table, record_id)
        self.seen_store.update_status(url, "pending")

        self.slack.notify_approval(
            fields.get("Name") or fields.get("Title", "Untitled"),
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

    def _records_or_backoff(self, loader, stats: dict[str, int]) -> list[dict] | None:
        try:
            return loader()
        except Exception as exc:
            if is_airtable_rate_limit_error(exc):
                logger.warning(
                    "Airtable rate-limited approval sync; skipping this interval: %s",
                    exc,
                )
                stats["rate_limited"] = 1
                return None
            raise

    def _sync_record(self, record: dict, mover, stats: dict[str, int], key: str, label: str) -> None:
        try:
            result = mover(record)
            if result is not False:
                stats[key] += 1
        except Exception as exc:
            if is_airtable_rate_limit_error(exc):
                logger.warning(
                    "Airtable rate-limited while moving %s; remaining records wait: %s",
                    label,
                    exc,
                )
                stats["rate_limited"] = 1
                raise
            logger.exception("Error moving %s: %s", label, exc)
            stats["errors"] += 1
            self.slack.notify_error(f"Approval sync failed ({label}): {exc}")

    def run(self) -> dict[str, int]:
        lock_path = Path(self.seen_store.db_path).parent / "approval_sync.lock"
        lock = FileLock(str(lock_path))
        with lock:
            return self._run_unlocked()

    def _run_unlocked(self) -> dict[str, int]:
        stats = {"approved": 0, "send_back": 0, "rejected": 0, "errors": 0, "rate_limited": 0}

        approved = self._records_or_backoff(self.airtable.list_pending_approved, stats)
        if approved is None:
            return stats
        for record in approved:
            try:
                self._sync_record(record, self._move_to_live, stats, "approved", "to live")
            except Exception:
                if stats.get("rate_limited"):
                    return stats
                raise

        send_back = self._records_or_backoff(self.airtable.list_live_send_back, stats)
        if send_back is None:
            return stats
        for record in send_back:
            try:
                self._sync_record(record, self._move_to_pending, stats, "send_back", "to pending")
            except Exception:
                if stats.get("rate_limited"):
                    return stats
                raise

        rejected = self._records_or_backoff(self.airtable.list_pending_rejected, stats)
        if rejected is None:
            return stats
        for record in rejected:
            try:
                self._handle_rejected(record)
                stats["rejected"] += 1
            except Exception as exc:
                if is_airtable_rate_limit_error(exc):
                    logger.warning(
                        "Airtable rate-limited while handling rejection; remaining wait: %s",
                        exc,
                    )
                    stats["rate_limited"] = 1
                    return stats
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
