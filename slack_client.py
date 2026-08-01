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


class SlackNotifier:
    """Post discovery and approval notifications via Slack incoming webhook."""

    def __init__(self, webhook_url: str | None = None, quiet_runs: bool | None = None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL", "")
        quiet = quiet_runs if quiet_runs is not None else os.getenv("SLACK_QUIET_RUNS", "true")
        self.quiet_runs = str(quiet).lower() in ("1", "true", "yes")

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
            logger.exception("Slack post failed: %s", exc)
            return False

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
            if self.quiet_runs:
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
            lines.append(f"• *{self._state_full(item.get('state', ''))}*: {item.get('title', 'Untitled')}")
        if len(items) > 10:
            lines.append(f"_…and {len(items) - 10} more_")

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "New MMIP policy batch", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": summary_text}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
        ]
        return self._post({"blocks": blocks, "text": f"{len(items)} new MMIP policies ready for review"})

    def notify_run_complete(self, analyzed: int, rejected: int, skipped: int, errors: int) -> bool:
        if self.quiet_runs and analyzed == 0 and errors == 0:
            return False
        text = (
            f"MMIP discovery run complete: {analyzed} analyzed, "
            f"{rejected} rejected, {skipped} skipped, {errors} errors"
        )
        return self._post({"text": text})

    def notify_approval(self, title: str, state: str, direction: str) -> bool:
        state_full = self._state_full(state)
        if direction == "to_live":
            text = f"Approved and published: *{title}* ({state_full}) is now live."
        else:
            text = f"Sent back to pending: *{title}* ({state_full}) needs another look."
        return self._post({"text": text})

    def notify_error(self, message: str) -> bool:
        return self._post({"text": f":warning: MMIP pipeline error: {message}"})
