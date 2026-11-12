"""Once-a-month fan-out of the tracker-wide monthly digest."""

from __future__ import annotations

import logging
from typing import Any

from subscriptions.config import subscriptions_enabled
from subscriptions.digest import _event_to_email_item
from subscriptions.mail import MailDeliveryError, send_monthly_subscription_digest
from subscriptions.monthly_archive import (
    load_events_for_month,
    period_label_for_month_key,
    previous_month_key,
    remove_events_for_month,
)
from subscriptions.monthly_summarize import summarize_month
from subscriptions.store import (
    filter_unnotified_monthly_keys,
    list_monthly_subscribers,
    mark_monthly_digest_notified,
)

logger = logging.getLogger(__name__)


def _watermark_key(email: str, month_key: str) -> str:
    return f"{email}|{month_key}"


def _apply_summary_overrides(
    events: list[dict[str, Any]],
    overrides: dict[str, str],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for event in events:
        item = _event_to_email_item(event)
        key = str(event.get("key") or "")
        if key and key in overrides:
            item["summary"] = overrides[key]
        items.append(item)
    # Stable order: state then title
    items.sort(key=lambda i: (i.get("state") or "", i.get("title") or ""))
    return items


def send_monthly_digests(*, month_key: str | None = None) -> dict[str, int | str]:
    """Build and send last month's digest to monthly subscribers.

    Safe to call on a schedule (e.g. 1st of each month). Idempotent per
    subscriber via ``email|YYYY-MM`` watermarks.
    """
    stats: dict[str, int | str] = {
        "month": "",
        "events": 0,
        "subscribers": 0,
        "emails_sent": 0,
        "emails_failed": 0,
        "emails_skipped": 0,
        "skipped_disabled": 0,
        "skipped_empty": 0,
        "events_cleared": 0,
    }
    if not subscriptions_enabled():
        stats["skipped_disabled"] = 1
        logger.info("Monthly digests skipped (STATE_SUBSCRIBE_ENABLED off)")
        return stats

    target_month = (month_key or previous_month_key()).strip()
    stats["month"] = target_month
    period_label = period_label_for_month_key(target_month)
    events = load_events_for_month(target_month)
    stats["events"] = len(events)

    subscribers = list_monthly_subscribers()
    stats["subscribers"] = len(subscribers)

    if not events:
        stats["skipped_empty"] = 1
        logger.info(
            "Monthly digests skipped — no archived events for %s",
            target_month,
        )
        return stats

    overview, overrides = summarize_month(period_label=period_label, events=events)
    items = _apply_summary_overrides(events, overrides)

    for email in subscribers:
        wm = _watermark_key(email, target_month)
        if not filter_unnotified_monthly_keys([wm]):
            stats["emails_skipped"] = int(stats["emails_skipped"]) + 1
            continue
        try:
            send_monthly_subscription_digest(
                email,
                period_label=period_label,
                overview=overview,
                items=items,
            )
        except MailDeliveryError:
            logger.exception("Monthly digest failed for %s", email)
            stats["emails_failed"] = int(stats["emails_failed"]) + 1
            continue
        except Exception:
            logger.exception("Monthly digest unexpected failure for %s", email)
            stats["emails_failed"] = int(stats["emails_failed"]) + 1
            continue
        mark_monthly_digest_notified([wm])
        stats["emails_sent"] = int(stats["emails_sent"]) + 1

    # Clear archive for the month once every subscriber was attempted or already sent.
    remaining = [
        email
        for email in subscribers
        if filter_unnotified_monthly_keys([_watermark_key(email, target_month)])
    ]
    if not remaining:
        stats["events_cleared"] = remove_events_for_month(target_month)

    logger.info(
        "Monthly digests done month=%s events=%d subscribers=%d sent=%d "
        "failed=%d skipped=%d cleared=%d",
        stats["month"],
        stats["events"],
        stats["subscribers"],
        stats["emails_sent"],
        stats["emails_failed"],
        stats["emails_skipped"],
        stats["events_cleared"],
    )
    return stats
