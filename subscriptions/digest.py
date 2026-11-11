"""Morning fan-out of queued Live bill events to state subscribers."""

from __future__ import annotations

import logging
from typing import Any

from public_api.serialize import bill_slug
from subscriptions.config import subscriptions_enabled
from subscriptions.digest_queue import load_events, remove_events
from subscriptions.email_brand import DEFAULT_PUBLIC_ORIGIN
from subscriptions.mail import MailDeliveryError, send_subscription_digest
from subscriptions.store import (
    filter_unnotified_digest_keys,
    list_subscribers,
    mark_digest_notified,
)

logger = logging.getLogger(__name__)


def _public_origin() -> str:
    import os

    return (
        os.getenv("NEXT_PUBLIC_SITE_URL")
        or os.getenv("PUBLIC_SITE_URL")
        or DEFAULT_PUBLIC_ORIGIN
    ).rstrip("/")


def public_bill_path(*, state: str, record_id: str, fields: dict[str, Any] | None = None) -> str:
    """Path for a Live bill on the public site."""
    slug = bill_slug(record_id, fields or {})
    code = (state or "Unknown").strip() or "Unknown"
    return f"/states/{code}/bills/{slug}"


def public_bill_url(
    *,
    state: str,
    record_id: str = "",
    fields: dict[str, Any] | None = None,
    public_path: str = "",
    fallback_url: str = "",
) -> str:
    origin = _public_origin()
    path = (public_path or "").strip()
    if not path and record_id:
        path = public_bill_path(state=state, record_id=record_id, fields=fields)
    if path:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{origin}{path if path.startswith('/') else '/' + path}"
    return (fallback_url or origin).strip() or origin


def _event_to_email_item(event: dict[str, Any]) -> dict[str, str]:
    state = str(event.get("state") or "")
    title = str(event.get("title") or "Policy update")
    summary = str(event.get("summary") or "")
    url = public_bill_url(
        state=state,
        record_id=str(event.get("record_id") or ""),
        public_path=str(event.get("public_path") or ""),
        fallback_url=str(event.get("url") or ""),
    )
    return {
        "title": title,
        "url": url,
        "state": state,
        "summary": summary,
    }


def send_morning_digests() -> dict[str, int]:
    """Fan out queued digest events to subscribers. Safe to call every morning."""
    stats = {
        "queued": 0,
        "eligible": 0,
        "emails_sent": 0,
        "emails_failed": 0,
        "events_cleared": 0,
        "skipped_disabled": 0,
    }
    if not subscriptions_enabled():
        stats["skipped_disabled"] = 1
        logger.info("Subscriber digests skipped (STATE_SUBSCRIBE_ENABLED off)")
        return stats

    events = load_events()
    stats["queued"] = len(events)
    if not events:
        logger.info("No pending subscriber digest events")
        return stats

    keys = [str(e.get("key") or "") for e in events if e.get("key")]
    unnotified_keys = set(filter_unnotified_digest_keys(keys))
    eligible = [e for e in events if str(e.get("key") or "") in unnotified_keys]
    stats["eligible"] = len(eligible)
    if not eligible:
        # All queued keys already notified — drop them.
        removed = remove_events(keys)
        stats["events_cleared"] = removed
        logger.info("Digest queue had only already-notified events; cleared=%d", removed)
        return stats

    subscribers = list_subscribers()
    sent_keys: set[str] = set()
    matched_keys: set[str] = set()

    for email, states in subscribers:
        state_set = set(states)
        matched = [
            e
            for e in eligible
            if str(e.get("state") or "") in state_set
        ]
        if not matched:
            continue
        for e in matched:
            key = str(e.get("key") or "")
            if key:
                matched_keys.add(key)
        items = [_event_to_email_item(e) for e in matched]
        state_labels = sorted({str(e.get("state") or "") for e in matched})
        try:
            send_subscription_digest(
                email,
                state_labels=state_labels,
                items=items,
            )
        except MailDeliveryError:
            logger.exception("Morning digest failed for %s", email)
            stats["emails_failed"] += 1
            continue
        except Exception:
            logger.exception("Morning digest unexpected failure for %s", email)
            stats["emails_failed"] += 1
            continue
        stats["emails_sent"] += 1
        for e in matched:
            key = str(e.get("key") or "")
            if key:
                sent_keys.add(key)

    # Orphans: no subscriber follows that state — drop so the queue cannot grow forever.
    orphan_keys = unnotified_keys - matched_keys
    # Already-notified leftovers still sitting in the queue file.
    stale_keys = set(keys) - unnotified_keys
    done_keys = sent_keys | orphan_keys | stale_keys
    if done_keys:
        mark_digest_notified(sent_keys | orphan_keys)
        stats["events_cleared"] = remove_events(done_keys)

    logger.info(
        "Morning digests done queued=%d eligible=%d sent=%d failed=%d cleared=%d",
        stats["queued"],
        stats["eligible"],
        stats["emails_sent"],
        stats["emails_failed"],
        stats["events_cleared"],
    )
    return stats
