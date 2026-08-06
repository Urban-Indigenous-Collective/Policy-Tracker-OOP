import logging
import os
import random
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

TEMPLATES = [
    "New policy drop from {state_full}!",
    "Hey — looks like {state_full} just introduced something.",
    "{state_full} has a new one for us.",
    "Heads up: {state_full} dropped a new MMIP policy.",
]


def _discovery_slack_always() -> bool:
    return os.getenv("DISCOVERY_SLACK_ALWAYS", "true").lower() in ("1", "true", "yes")


class SlackNotifier:
    """Post discovery and approval notifications via Slack incoming webhook."""

    def __init__(
        self,
        webhook_url: str | None = None,
        quiet_runs: bool | None = None,
        backfill_summary: bool = False,
    ):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL", "")
        quiet = quiet_runs if quiet_runs is not None else os.getenv("SLACK_QUIET_RUNS", "true")
        self.quiet_runs = str(quiet).lower() in ("1", "true", "yes")
        # Backfill / deferred digests should always post summaries.
        if backfill_summary:
            self.quiet_runs = False

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def _state_full(self, state: str) -> str:
        code = (state or "").strip().upper()
        if len(code) == 2 and code in STATE_NAMES:
            return STATE_NAMES[code]
        return state or "Unknown"

    def _post(self, payload: dict[str, Any]) -> bool:
        if not self.enabled:
            logger.debug("Slack disabled, skipping notification")
            return False
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=15)
            response.raise_for_status()
            return True
        except Exception as exc:
            body = ""
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                body = (exc.response.text or "")[:500]
            logger.exception("Slack post failed: %s %s", exc, body)
            return False

    @staticmethod
    def _chunk_lines(lines: list[str], max_chars: int = 2800) -> list[list[str]]:
        """Split mrkdwn lines so each chunk stays under Slack's section text limit."""
        chunks: list[list[str]] = []
        current: list[str] = []
        size = 0
        for line in lines:
            line_len = len(line) + (1 if current else 0)
            if current and size + line_len > max_chars:
                chunks.append(current)
                current = [line]
                size = len(line)
            else:
                current.append(line)
                size += line_len
        if current:
            chunks.append(current)
        return chunks

    def _build_discovery_blocks(
        self,
        state: str,
        title: str,
        summary: str,
        categories: str,
        confidence: float,
        source_url: str,
        pending_url: str = "",
    ) -> list[dict]:
        state_full = self._state_full(state)
        headline = random.choice(TEMPLATES).format(state=state, state_full=state_full)
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": headline, "emoji": True}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*\n{summary[:300]}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"*State:* {state_full}"},
                    {"type": "mrkdwn", "text": f"*Categories:* {categories or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*Confidence:* {confidence:.0%}"},
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Source"},
                        "url": source_url,
                    }
                ],
            },
        ]
        if pending_url:
            blocks[-1]["elements"].append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Review in Airtable"},
                    "url": pending_url,
                }
            )
        return blocks

    def notify_discovery(
        self,
        state: str,
        title: str,
        summary: str,
        categories: str,
        confidence: float,
        source_url: str,
        pending_url: str = "",
    ) -> bool:
        blocks = self._build_discovery_blocks(
            state, title, summary, categories, confidence, source_url, pending_url
        )
        return self._post({"blocks": blocks, "text": f"New MMIP policy from {state}: {title}"})

    def notify_discovery_batch(self, items: list[dict[str, Any]]) -> bool:
        if not items:
            if self.quiet_runs and not _discovery_slack_always():
                return False
            return self._post({"text": "Nightly MMIP discovery run complete — no new policies found."})

        if len(items) <= 5:
            ok = True
            for item in items:
                ok = self.notify_discovery(**item) and ok
            return ok

        states = sorted({self._state_full(i.get("state", "")) for i in items})
        summary_text = f"*{len(items)} new MMIP policies* ready for review from: {', '.join(states)}"
        lines = []
        for item in items[:10]:
            lines.append(
                f"• *{self._state_full(item.get('state', ''))}*: {item.get('title', 'Untitled')}"
            )
        if len(items) > 10:
            lines.append(f"_…and {len(items) - 10} more_")

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "New MMIP policy batch", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": summary_text}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
        ]
        return self._post({"blocks": blocks, "text": f"{len(items)} new MMIP policies ready for review"})

    def notify_run_complete(
        self,
        analyzed: int = 0,
        rejected: int = 0,
        skipped: int = 0,
        errors: int = 0,
        *,
        discovered: int | None = None,
        by_state: dict[str, Any] | None = None,
        run_started_at: str = "",
        run_finished_at: str = "",
        sources_attempted: dict[str, Any] | None = None,
        always_notify: bool | None = None,
    ) -> bool:
        if always_notify is None:
            always_notify = _discovery_slack_always()
        if self.quiet_runs and not always_notify and analyzed == 0 and errors == 0:
            return False

        parts = [
            f"MMIP discovery run complete: {analyzed} analyzed, "
            f"{rejected} rejected, {skipped} skipped, {errors} errors"
        ]
        if discovered is not None:
            parts[0] = (
                f"MMIP discovery run complete: {discovered} discovered, {analyzed} analyzed, "
                f"{rejected} rejected, {skipped} skipped, {errors} errors"
            )
        if run_started_at:
            parts.append(f"Started: {run_started_at}")
        if run_finished_at:
            parts.append(f"Finished: {run_finished_at}")
        if sources_attempted:
            bits = ", ".join(f"{k}={v}" for k, v in sorted(sources_attempted.items()))
            parts.append(f"Sources: {bits}")
        if by_state:
            parts.append(f"States touched: {len(by_state)}")
        return self._post({"text": "\n".join(parts)})

    def notify_status_refresh_complete(
        self,
        checked: int = 0,
        updated: int = 0,
        unchanged: int = 0,
        skipped_non_legiscan: int = 0,
        resolve_failed: int = 0,
        getbill_failed: int = 0,
        identity_mismatch: int = 0,
        errors: int = 0,
        always_notify: bool | None = None,
    ) -> bool:
        """Heartbeat summary after the LegiScan status refresh pass."""
        if always_notify is None:
            always_notify = _discovery_slack_always()
        if (
            self.quiet_runs
            and not always_notify
            and updated == 0
            and identity_mismatch == 0
            and errors == 0
            and resolve_failed == 0
            and getbill_failed == 0
        ):
            return False
        text = (
            "MMIP status refresh complete: "
            f"checked={checked}, updated={updated}, unchanged={unchanged}, "
            f"skipped_non_legiscan={skipped_non_legiscan}, "
            f"resolve_failed={resolve_failed}, getbill_failed={getbill_failed}, "
            f"identity_mismatch={identity_mismatch}, errors={errors}"
        )
        return self._post({"text": text})

    def notify_approval(self, title: str, state: str, direction: str) -> bool:
        state_full = self._state_full(state)
        if direction == "to_live":
            text = f"Approved and published: *{title}* ({state_full}) is now live."
        else:
            text = f"Sent back to pending: *{title}* ({state_full}) needs another look."
        return self._post({"text": text})

    def notify_status_changes(self, items: list[dict[str, Any]]) -> bool:
        """Post legislative status updates for existing Pending/Live bills."""
        if not items:
            return False

        if len(items) == 1:
            return self._post(self._build_status_change_payload(items[0]))

        lines = []
        for item in items:
            state_full = self._state_full(item.get("state", ""))
            change_bits = ", ".join(
                f"{c['field']}: {c['old']} → {c['new']}" for c in (item.get("changes") or [])
            )
            lines.append(
                f"• *{state_full}* ({item.get('table', 'Pending')}): "
                f"{item.get('title', 'Untitled')} — {change_bits}"
            )

        ok = True
        chunks = self._chunk_lines(lines)
        for index, chunk in enumerate(chunks):
            suffix = f" ({index + 1}/{len(chunks)})" if len(chunks) > 1 else ""
            blocks: list[dict[str, Any]] = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{len(items)} bill status updates{suffix}",
                        "emoji": True,
                    },
                },
                {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(chunk)}},
            ]
            ok = self._post(
                {
                    "blocks": blocks,
                    "text": f"{len(items)} bill status updates ready for review{suffix}",
                }
            ) and ok
        return ok

    def _build_status_change_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        state_full = self._state_full(item.get("state", ""))
        title = item.get("title", "Untitled")
        table_label = item.get("table", "Pending")
        source_url = item.get("source_url", "")
        change_lines = [
            f"• *{c['field']}:* {c['old']} → {c['new']}" for c in (item.get("changes") or [])
        ]
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Bill status update",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*\n{state_full} · {table_label}\n" + "\n".join(change_lines),
                },
            },
        ]
        if source_url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View on LegiScan"},
                            "url": source_url,
                        }
                    ],
                }
            )
        return {"blocks": blocks, "text": f"Status update: {title} ({state_full})"}

    def notify_identity_mismatches(self, items: list[dict[str, Any]]) -> bool:
        """Post bill identity mismatches that need human review."""
        if not items:
            return False

        if len(items) == 1:
            return self._post(self._build_identity_mismatch_payload(items[0]))

        lines = []
        for item in items:
            state_full = self._state_full(item.get("state", ""))
            action_note = (
                "moved to Pending"
                if item.get("action") == "sent_to_pending"
                else "flagged on Pending"
            )
            lines.append(
                f"• *{state_full}*: {item.get('title', 'Untitled')} — "
                f"Airtable `{item.get('airtable_bill_number', '?')}` vs "
                f"LegiScan `{item.get('legiscan_bill_number', '?')}` ({action_note})"
            )

        ok = True
        chunks = self._chunk_lines(lines)
        for index, chunk in enumerate(chunks):
            suffix = f" ({index + 1}/{len(chunks)})" if len(chunks) > 1 else ""
            blocks: list[dict[str, Any]] = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{len(items)} identity mismatches needing review{suffix}",
                        "emoji": True,
                    },
                },
                {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(chunk)}},
            ]
            ok = self._post(
                {
                    "blocks": blocks,
                    "text": f"{len(items)} identity mismatches needing review{suffix}",
                }
            ) and ok
        return ok

    def _build_identity_mismatch_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        state_full = self._state_full(item.get("state", ""))
        title = item.get("title", "Untitled")
        table_label = item.get("table", "Pending")
        source_url = item.get("source_url", "")
        airtable_bill = item.get("airtable_bill_number", "?")
        legiscan_bill = item.get("legiscan_bill_number", "?")
        action_note = (
            "Moved back to Pending for review."
            if item.get("action") == "sent_to_pending"
            else "Flagged on Pending for review."
        )
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Identity mismatch needing review",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{title}*\n{state_full} · {table_label}\n"
                        f"• *Airtable bill:* `{airtable_bill}`\n"
                        f"• *LegiScan bill:* `{legiscan_bill}`\n"
                        f"• URL resolved to the wrong bill. {action_note}"
                    ),
                },
            },
        ]
        if source_url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View on LegiScan"},
                            "url": source_url,
                        }
                    ],
                }
            )
        return {"blocks": blocks, "text": f"Identity mismatch: {title} ({state_full})"}

    def notify_error(self, message: str) -> bool:
        return self._post({"text": f":warning: MMIP pipeline error: {message}"})
