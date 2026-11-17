"""Slack alerts for subscription signup / unsubscribe (#mmiwr-subscribers).

Uses a dedicated incoming webhook (``SLACK_SUBSCRIBERS_WEBHOOK_URL``) so these
ops pings stay out of the discovery/review channel.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from slack_client import state_display_name

logger = logging.getLogger(__name__)


def subscribers_webhook_url() -> str:
    return (os.getenv("SLACK_SUBSCRIBERS_WEBHOOK_URL") or "").strip()


def subscribers_slack_enabled() -> bool:
    return bool(subscribers_webhook_url())


def _post(text: str) -> bool:
    url = subscribers_webhook_url()
    if not url:
        logger.debug("SLACK_SUBSCRIBERS_WEBHOOK_URL unset; skip subscriber alert")
        return False
    payload: dict[str, Any] = {"text": text}
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as exc:
        body = ""
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            body = (exc.response.text or "")[:300]
        logger.exception("subscriber Slack alert failed: %s %s", exc, body)
        return False


def _label_for_state(state: str) -> str:
    raw = (state or "").strip()
    if raw.lower() == "national":
        return "National"
    return state_display_name(raw) or raw


def notify_state_subscribed(email: str, state: str) -> bool:
    """Alert when someone newly opts into a state or National updates."""
    label = _label_for_state(state)
    kind = "National" if label == "National" else "state"
    return _post(f":inbox_tray: New {kind} subscription — *{email}* → {label}")


def notify_state_unsubscribed(
    email: str, *, removed: str, remaining: list[str] | None = None
) -> bool:
    """Alert when someone drops a state/National list or everything."""
    left = remaining or []
    if removed == "all":
        return _post(
            f":outbox_tray: Unsubscribed from *all* state/national updates — *{email}*"
        )
    label = _label_for_state(removed)
    kind = "National" if label == "National" else "state"
    suffix = ""
    if left:
        pretty = ", ".join(_label_for_state(s) for s in left)
        suffix = f" (still: {pretty})"
    else:
        suffix = " (no remaining state/national subscriptions)"
    return _post(
        f":outbox_tray: Unsubscribed from {kind} updates — *{email}* ← {label}{suffix}"
    )


def notify_monthly_subscribed(email: str) -> bool:
    """Alert when someone newly opts into the tracker-wide monthly digest."""
    return _post(f":calendar: New monthly digest subscription — *{email}*")


def _format_state_list(states: list[str]) -> str:
    """Human list: Alaska / Alaska and Florida / Alaska, Florida, and Maine."""
    labels = [_label_for_state(s) for s in states if str(s or "").strip()]
    # Dedupe while keeping sorted order from caller
    seen: set[str] = set()
    unique: list[str] = []
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        unique.append(label)
    if not unique:
        return "their followed states"
    if len(unique) == 1:
        return unique[0]
    if len(unique) == 2:
        return f"{unique[0]} and {unique[1]}"
    return f"{', '.join(unique[:-1])}, and {unique[-1]}"


def notify_morning_digest_run(
    *, emails_sent: int, states: list[str] | None = None
) -> bool:
    """Alert after morning state/National subscriber emails go out."""
    count = int(emails_sent or 0)
    if count <= 0:
        return False
    who = "community member" if count == 1 else "community members"
    where = _format_state_list(states or [])
    return _post(
        f":mega: *{count}* {who} were just notified of updates in {where}"
    )


def notify_monthly_digest_run(stats: dict[str, Any]) -> bool:
    """Alert after the scheduled monthly digest fan-out completes."""
    month = str(stats.get("month") or "").strip() or "unknown"
    events = int(stats.get("events") or 0)
    subscribers = int(stats.get("subscribers") or 0)
    sent = int(stats.get("emails_sent") or 0)
    failed = int(stats.get("emails_failed") or 0)
    skipped = int(stats.get("emails_skipped") or 0)

    if int(stats.get("skipped_empty") or 0):
        return _post(
            f":mailbox_with_no_mail: Monthly digest skipped — *{month}* "
            f"(no archived events; {subscribers} subscriber"
            f"{'' if subscribers == 1 else 's'})"
        )

    return _post(
        f":mailbox_with_mail: Monthly digest sent — *{month}* — "
        f"{events} event{'' if events == 1 else 's'} → "
        f"{subscribers} subscriber{'' if subscribers == 1 else 's'} "
        f"({sent} sent, {failed} failed, {skipped} already sent)"
    )