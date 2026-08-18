"""Re-fetch LegiScan metadata for existing Pending and Live bills."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from approval_sync import ApprovalSync
from airtable_client import AirtableClient
from airtable_coercion import coerce_bill_fields
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, REVIEW_STATUS_REJECTED
from api_client import APIClient
from content_guard import merge_warnings
from discovery.legiscan_quota import is_legiscan_limit_error, legiscan_quota_payload, merge_legiscan_quota
from discovery.models import utc_now_iso
from discovery.seen_store import SeenStore
from discovery.slack_report import (
    discovery_slack_always,
    merge_status_refresh_report,
    should_defer_slack,
)
from legiscan_processor import (
    TRACKED_STATUS_FIELD_NAMES,
    LegiScanProcessor,
    normalize_bill_number,
    parse_legiscan_bill_url,
)
from slack_client import SlackNotifier

logger = logging.getLogger(__name__)

_SESSION_YEAR_RE = re.compile(r"(20\d{2})")


def status_refresh_log_path() -> Path:
    db_path = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
    return db_path.parent / "status_refresh_runs.jsonl"


def append_status_refresh_run_log(
    stats: "StatusRefreshStats",
    *,
    dry_run: bool,
    run_at: str,
) -> None:
    """Append one JSON line per status refresh run for later audit."""
    if dry_run:
        return
    path = status_refresh_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_at": run_at,
        "checked": stats.checked,
        "updated": stats.updated,
        "unchanged": stats.unchanged,
        "skipped_non_legiscan": stats.skipped_non_legiscan,
        "resolve_failed": stats.resolve_failed,
        "getbill_failed": stats.getbill_failed,
        "skipped_unchanged_hash": stats.skipped_unchanged_hash,
        "masterlists_fetched": stats.masterlists_fetched,
        "getbills_fetched": stats.getbills_fetched,
        "identity_mismatch": stats.identity_mismatch,
        "identity_mismatch_items": stats.identity_mismatch_items,
        "errors": stats.errors,
        "changes": stats.status_items,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    logger.info("Status refresh run log appended to %s", path)


@dataclass
class StatusRefreshStats:
    checked: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_non_legiscan: int = 0
    skipped_unchanged_hash: int = 0
    masterlists_fetched: int = 0
    getbills_fetched: int = 0
    errors: int = 0
    resolve_failed: int = 0
    getbill_failed: int = 0
    identity_mismatch: int = 0
    legiscan_limited: bool = False
    legiscan_limit_reason: str = ""
    status_items: list[dict[str, Any]] = field(default_factory=list)
    identity_mismatch_items: list[dict[str, Any]] = field(default_factory=list)


def format_identity_mismatch_warning(
    airtable_bill_number: str,
    legiscan_bill_number: str,
) -> str:
    return (
        f"identity mismatch: Airtable bill {airtable_bill_number} vs "
        f"LegiScan bill {legiscan_bill_number}; URL resolved to wrong bill"
    )


def _year_from_fields(fields: dict[str, Any], url: str = "") -> int | None:
    parsed = parse_legiscan_bill_url(url)
    if parsed:
        return parsed[2]
    session = str(fields.get("Session") or "")
    match = _SESSION_YEAR_RE.search(session)
    if match:
        return int(match.group(1))
    return None


def _should_update_last_update(old_val: str, new_val: str, other_changed: bool) -> bool:
    if other_changed:
        return True
    if not old_val or not new_val:
        return old_val != new_val
    return new_val >= old_val


def diff_status_fields(
    current_fields: dict[str, Any],
    fresh_fields: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Return (airtable_update_fields, slack_change_list)."""
    coerced_fresh = coerce_bill_fields(fresh_fields)
    coerced_current = coerce_bill_fields(
        {name: current_fields.get(name, "") for name in TRACKED_STATUS_FIELD_NAMES}
    )
    updates: dict[str, Any] = {}
    changes: list[dict[str, str]] = []

    status_changed = str(coerced_current.get("Status", "") or "") != str(
        coerced_fresh.get("Status", "") or ""
    )
    progression_changed = str(coerced_current.get("Progression", "") or "") != str(
        coerced_fresh.get("Progression", "") or ""
    )
    other_status_changed = status_changed or progression_changed

    for name in TRACKED_STATUS_FIELD_NAMES:
        old_val = str(coerced_current.get(name, "") or "")
        new_val = str(coerced_fresh.get(name, "") or "")
        if old_val == new_val:
            continue
        if name == "Last Update" and not _should_update_last_update(
            old_val, new_val, other_status_changed
        ):
            continue
        updates[name] = coerced_fresh[name]
        changes.append({"field": name, "old": old_val, "new": new_val})
    return updates, changes


class StatusRefreshPipeline:
    """Refresh legislative status fields for tracked Pending and Live bills."""

    def __init__(
        self,
        api_client: APIClient,
        legiscan_processor: LegiScanProcessor,
        airtable: AirtableClient | None = None,
        seen_store: SeenStore | None = None,
        slack: SlackNotifier | None = None,
        dry_run: bool = False,
    ):
        self.api_client = api_client
        self.legiscan = legiscan_processor
        self.airtable = airtable or AirtableClient()
        self.seen_store = seen_store or SeenStore(
            os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
        )
        self.slack = slack or SlackNotifier()
        self.dry_run = dry_run
        self._masterlist_sessions_loaded: set[str] = set()

    def _legiscan_state_code(self, state: str, url: str = "") -> str:
        code = (state or "").strip().upper()
        if code in ("NATIONAL", "US", "FEDERAL", "DC"):
            if code == "NATIONAL" or code == "FEDERAL":
                return "US"
            return code
        parsed = parse_legiscan_bill_url(url)
        if parsed:
            return parsed[0]
        return code

    def _resolve_session_id_for_record(
        self,
        fields: dict[str, Any],
        overview_url: str,
        seen_record: dict[str, Any] | None,
    ) -> str | None:
        if seen_record and seen_record.get("session_id"):
            return str(seen_record["session_id"])
        state_code = self._legiscan_state_code(str(fields.get("State") or ""), overview_url)
        year = _year_from_fields(fields, overview_url)
        return self.legiscan.resolve_session_id(state_code, year)

    def _track_masterlist_fetch(self, session_id: str, stats: StatusRefreshStats) -> None:
        if session_id and session_id not in self._masterlist_sessions_loaded:
            self._masterlist_sessions_loaded.add(session_id)
            stats.masterlists_fetched += 1

    def _masterlist_entry(
        self,
        session_id: str,
        bill_id: str,
        stats: StatusRefreshStats,
    ) -> dict | None:
        if not session_id:
            return None
        self._track_masterlist_fetch(session_id, stats)
        return self.legiscan.masterlist_entry_for_bill(session_id, bill_id)

    def _record_url(self, record: dict) -> str:
        fields = record.get("fields") or {}
        return fields.get(BILL_OVERVIEW_LINK_FIELD) or fields.get("Bill Overview") or ""

    def _resolve_bill_id_for_record(self, fields: dict[str, Any], overview_url: str) -> str | None:
        state = (fields.get("State") or "").strip()
        bill_number = (fields.get("Bill Number") or "").strip()
        year = _year_from_fields(fields, overview_url)
        hints = {"state": state, "bill_number": bill_number, "year": year}

        seen = self.seen_store.get(overview_url)
        if seen and seen.get("external_id"):
            return str(seen["external_id"])

        if state and bill_number:
            seen = self.seen_store.get_by_state_bill(state, bill_number)
            if seen and seen.get("external_id"):
                return str(seen["external_id"])

        bill_id = self.legiscan.resolve_bill_id(overview_url, **hints)
        if bill_id:
            return bill_id

        bill_text = fields.get("Bill Text") or ""
        if bill_text and self.legiscan.is_legiscan_url(bill_text) and bill_text != overview_url:
            bill_id = self.legiscan.resolve_bill_id(bill_text, **hints)
            if bill_id:
                return bill_id

        if state and bill_number and year:
            found = self.legiscan.search_bill_id(state, bill_number, year)
            if found:
                return found

        return None

    def _persist_bill_metadata(
        self,
        url: str,
        bill_details: dict,
        bill_id: str,
        *,
        state: str = "",
        session_id: str = "",
    ) -> None:
        if self.dry_run:
            return
        bill = bill_details.get("bill") or {}
        change_hash = str(bill.get("change_hash") or "")
        canonical_url = self.legiscan.get_bill_link(bill)
        if canonical_url and canonical_url != "N/A":
            self.seen_store.upsert(
                canonical_url,
                source="LegiScan",
                state=state or bill.get("state", ""),
                external_id=bill_id,
                session_id=session_id,
                change_hash=change_hash,
                status="pending",
            )
        seen = self.seen_store.get(url)
        if seen:
            self.seen_store.update_metadata(
                url,
                external_id=bill_id,
                session_id=session_id,
                change_hash=change_hash,
            )
        elif url != canonical_url:
            self.seen_store.upsert(
                url,
                source="LegiScan",
                state=state or bill.get("state", ""),
                external_id=bill_id,
                session_id=session_id,
                change_hash=change_hash,
                status="pending",
            )

    def _silent_approval_sync(self) -> ApprovalSync:
        """Approval sync without immediate Slack (digest handles notifications)."""
        disabled_slack = SlackNotifier(webhook_url="")
        return ApprovalSync(self.airtable, self.seen_store, disabled_slack)

    def _handle_identity_mismatch(
        self,
        record: dict,
        table_label: str,
        table,
        fields: dict[str, Any],
        *,
        title: str,
        state: str,
        url: str,
        airtable_bill_number: str,
        legiscan_bill_number: str,
        stats: StatusRefreshStats,
    ) -> None:
        stats.identity_mismatch += 1
        warning = format_identity_mismatch_warning(
            str(fields.get("Bill Number") or airtable_bill_number),
            legiscan_bill_number,
        )
        logger.warning(
            "Bill number identity mismatch for %s (%s): "
            "Airtable=%s LegiScan=%s — flagging for review",
            title,
            state,
            fields.get("Bill Number"),
            legiscan_bill_number,
        )

        stats.identity_mismatch_items.append(
            {
                "title": title,
                "state": state,
                "table": table_label,
                "airtable_bill_number": str(fields.get("Bill Number") or airtable_bill_number),
                "legiscan_bill_number": legiscan_bill_number,
                "source_url": url,
                "action": "sent_to_pending" if table_label == "Live" else "flagged",
            }
        )

        if not self.dry_run:
            if table_label == "Live":
                updated_fields = dict(fields)
                updated_fields["Validation Warnings"] = merge_warnings(
                    fields.get("Validation Warnings", ""),
                    [warning],
                )
                # Only write mutable fields — full field dumps include computed columns.
                self.airtable.update_record(
                    table,
                    record["id"],
                    {
                        "Validation Warnings": updated_fields["Validation Warnings"],
                    },
                )
                move_record = {**record, "fields": updated_fields}
                self._silent_approval_sync()._move_to_pending(move_record)
            else:
                self.airtable.update_record(
                    table,
                    record["id"],
                    {
                        "Validation Warnings": merge_warnings(
                            fields.get("Validation Warnings", ""),
                            [warning],
                        ),
                    },
                )

    def _maybe_repair_overview_url(
        self,
        overview_url: str,
        bill_details: dict,
        updates: dict[str, Any],
        changes: list[dict[str, str]],
    ) -> None:
        bill = bill_details.get("bill") or {}
        canonical = self.legiscan.get_bill_link(bill)
        if not canonical or canonical == "N/A" or canonical == overview_url:
            return
        updates[BILL_OVERVIEW_LINK_FIELD] = canonical
        changes.append(
            {
                "field": BILL_OVERVIEW_LINK_FIELD,
                "old": overview_url,
                "new": canonical,
            }
        )

    def _refresh_record(
        self,
        record: dict,
        table_label: str,
        table,
        stats: StatusRefreshStats,
    ) -> None:
        record_id = record["id"]
        fields = record.get("fields") or {}
        url = self._record_url(record)
        title = fields.get("Name") or fields.get("Bill Number") or "Untitled"
        state = fields.get("State") or ""

        if not url or not self.legiscan.is_legiscan_url(url):
            stats.skipped_non_legiscan += 1
            logger.debug("Skipping non-LegiScan record: %s", title)
            return

        stats.checked += 1
        try:
            seen_record = self.seen_store.get(url)
            bill_id = self._resolve_bill_id_for_record(fields, url)
            if not bill_id:
                stats.resolve_failed += 1
                logger.warning("Could not resolve bill_id for %s", url)
                return

            session_id = self._resolve_session_id_for_record(fields, url, seen_record) or ""
            stored_hash = str((seen_record or {}).get("change_hash") or "")
            master_entry = self._masterlist_entry(session_id, bill_id, stats)
            master_hash = str((master_entry or {}).get("change_hash") or "")

            if (
                session_id
                and master_hash
                and stored_hash
                and master_hash == stored_hash
            ):
                stats.skipped_unchanged_hash += 1
                stats.unchanged += 1
                if session_id and not (seen_record or {}).get("session_id"):
                    if not self.dry_run:
                        self.seen_store.update_metadata(url, session_id=session_id)
                logger.debug(
                    "Skipping unchanged bill_id=%s session=%s hash=%s",
                    bill_id,
                    session_id,
                    master_hash,
                )
                return

            if master_entry:
                airtable_bill_number = normalize_bill_number(
                    str(fields.get("Bill Number") or "")
                )
                master_bill_number = normalize_bill_number(
                    str(master_entry.get("number") or "")
                )
                if (
                    airtable_bill_number
                    and master_bill_number
                    and airtable_bill_number != master_bill_number
                ):
                    self._handle_identity_mismatch(
                        record,
                        table_label,
                        table,
                        fields,
                        title=title,
                        state=state,
                        url=url,
                        airtable_bill_number=airtable_bill_number,
                        legiscan_bill_number=str(master_entry.get("number") or ""),
                        stats=stats,
                    )
                    return

            stats.getbills_fetched += 1
            bill_details = self.api_client.get_bill_details(bill_id)
            if not bill_details or not isinstance(bill_details, dict) or "bill" not in bill_details:
                stats.getbill_failed += 1
                if getattr(self.api_client, "quota_exhausted", False) or self.api_client.response_indicates_overlimit(
                    bill_details if isinstance(bill_details, dict) else None
                ):
                    stats.legiscan_limited = True
                    stats.legiscan_limit_reason = (
                        getattr(self.api_client, "last_error_alert", "")
                        or "LegiScan API monthly limit reached"
                    )
                    logger.warning(
                        "Status refresh stopping after getBill failure (LegiScan quota): bill_id=%s",
                        bill_id,
                    )
                    return
                if stats.getbill_failed >= 2 and stats.updated == 0 and stats.unchanged == 0:
                    stats.legiscan_limited = True
                    stats.legiscan_limit_reason = (
                        f"LegiScan getBill failed {stats.getbill_failed} times with no successes"
                    )
                    logger.warning(
                        "Status refresh stopping after repeated getBill failures (likely quota)"
                    )
                    return
                logger.warning("getBill failed for bill_id=%s url=%s", bill_id, url)
                return

            bill = bill_details.get("bill") or {}
            airtable_bill_number = normalize_bill_number(str(fields.get("Bill Number") or ""))
            legiscan_bill_number = normalize_bill_number(str(bill.get("bill_number") or ""))
            if (
                airtable_bill_number
                and legiscan_bill_number
                and airtable_bill_number != legiscan_bill_number
            ):
                self._handle_identity_mismatch(
                    record,
                    table_label,
                    table,
                    fields,
                    title=title,
                    state=state,
                    url=url,
                    airtable_bill_number=airtable_bill_number,
                    legiscan_bill_number=str(bill.get("bill_number") or ""),
                    stats=stats,
                )
                return

            self._persist_bill_metadata(
                url,
                bill_details,
                bill_id,
                state=state,
                session_id=session_id,
            )
            fresh = self.legiscan.extract_status_fields(bill_details)
            updates, changes = diff_status_fields(fields, fresh)
            self._maybe_repair_overview_url(url, bill_details, updates, changes)

            if not updates:
                stats.unchanged += 1
                logger.debug("No status change for %s %s", state, title)
                return

            logger.info(
                "Status change for %s (%s): %s",
                title,
                table_label,
                ", ".join(f"{c['field']}: {c['old']} -> {c['new']}" for c in changes),
            )

            if not self.dry_run:
                self.airtable.update_record(table, record_id, updates)

            stats.updated += 1
            canonical = self.legiscan.get_bill_link(bill_details.get("bill") or {})
            stats.status_items.append(
                {
                    "title": title,
                    "state": state,
                    "table": table_label,
                    "source_url": canonical if canonical and canonical != "N/A" else url,
                    "changes": [c for c in changes if c["field"] != BILL_OVERVIEW_LINK_FIELD],
                }
            )
        except Exception as exc:
            if is_legiscan_limit_error(exc):
                stats.legiscan_limited = True
                stats.legiscan_limit_reason = str(exc)
                logger.warning("Status refresh stopped (LegiScan quota): %s", exc)
                return
            stats.errors += 1
            logger.exception("Status refresh failed for %s: %s", url, exc)

    def run(self) -> StatusRefreshStats:
        stats = StatusRefreshStats()
        self._masterlist_sessions_loaded.clear()
        logger.info("Starting status refresh pass (dry_run=%s)", self.dry_run)

        try:
            pending_records = self.airtable.list_pending_for_refresh()
            for record in pending_records:
                if stats.legiscan_limited:
                    break
                review = (record.get("fields") or {}).get("Review Status")
                if review == REVIEW_STATUS_REJECTED:
                    continue
                self._refresh_record(record, "Pending", self.airtable.pending_table, stats)

            if not stats.legiscan_limited:
                for record in self.airtable.all_live_records():
                    self._refresh_record(record, "Live", self.airtable.live_table, stats)
        except Exception as exc:
            if is_legiscan_limit_error(exc):
                stats.legiscan_limited = True
                stats.legiscan_limit_reason = str(exc)
                logger.warning("Status refresh aborted (LegiScan quota): %s", exc)
            else:
                raise

        logger.info(
            "Status refresh finished: checked=%d updated=%d unchanged=%d "
            "skipped_unchanged_hash=%d masterlists_fetched=%d getbills_fetched=%d "
            "skipped_non_legiscan=%d resolve_failed=%d getbill_failed=%d "
            "identity_mismatch=%d errors=%d",
            stats.checked,
            stats.updated,
            stats.unchanged,
            stats.skipped_unchanged_hash,
            stats.masterlists_fetched,
            stats.getbills_fetched,
            stats.skipped_non_legiscan,
            stats.resolve_failed,
            stats.getbill_failed,
            stats.identity_mismatch,
            stats.errors,
        )

        self.api_client.log_stats()

        run_at = utc_now_iso()
        append_status_refresh_run_log(stats, dry_run=self.dry_run, run_at=run_at)

        if self.dry_run:
            return stats

        refresh_stats = {
            "checked": stats.checked,
            "updated": stats.updated,
            "unchanged": stats.unchanged,
            "skipped_unchanged_hash": stats.skipped_unchanged_hash,
            "masterlists_fetched": stats.masterlists_fetched,
            "getbills_fetched": stats.getbills_fetched,
            "skipped_non_legiscan": stats.skipped_non_legiscan,
            "resolve_failed": stats.resolve_failed,
            "getbill_failed": stats.getbill_failed,
            "identity_mismatch": stats.identity_mismatch,
            "legiscan_limited": stats.legiscan_limited,
            "legiscan_limit_reason": stats.legiscan_limit_reason,
            "errors": stats.errors,
        }
        if should_defer_slack():
            merge_status_refresh_report(
                stats.status_items,
                refresh_stats,
                run_at=run_at,
                identity_mismatch_items=stats.identity_mismatch_items,
                legiscan_quota=(
                    legiscan_quota_payload(
                        reason=stats.legiscan_limit_reason,
                        status_refresh_limited=True,
                    )
                    if stats.legiscan_limited
                    else None
                ),
            )
        else:
            if stats.status_items:
                self.slack.notify_status_changes(stats.status_items)
            if stats.identity_mismatch_items:
                self.slack.notify_identity_mismatches(stats.identity_mismatch_items)
            self.slack.notify_status_refresh_complete(
                **refresh_stats,
                always_notify=discovery_slack_always(),
            )

        return stats


def build_pipeline(dry_run: bool = False) -> StatusRefreshPipeline:
    legiscan_key = os.getenv("LEGISCAN_KEY")
    if not legiscan_key:
        raise ValueError("LEGISCAN_KEY must be set")
    api_client = APIClient(legiscan_key)
    legiscan = LegiScanProcessor(indigenous_db=None, api_client=api_client)
    return StatusRefreshPipeline(api_client, legiscan, dry_run=dry_run)
