"""Month-keyed archive of Live bill events for the monthly digest.

Morning digests clear ``pending_subscriber_digest.json`` after fan-out, so
monthly sends need a durable copy. Events are dual-written from
``digest_queue.enqueue_event``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_lock = threading.RLock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def monthly_archive_path() -> Path:
    override = (os.getenv("STATE_SUBSCRIBE_MONTHLY_ARCHIVE_PATH") or "").strip()
    if override:
        return Path(override)
    db_path = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
    return db_path.parent / "monthly_digest_archive.json"


def _empty_archive() -> dict[str, Any]:
    return {"events": []}


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_archive()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("monthly digest archive unreadable (%s); starting empty", exc)
        return _empty_archive()
    if not isinstance(data, dict):
        return _empty_archive()
    events = data.get("events")
    if not isinstance(events, list):
        events = []
    return {"events": events}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def digest_timezone() -> ZoneInfo:
    name = (os.getenv("DISCOVERY_TZ") or "America/New_York").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("America/New_York")


def month_key_for(dt: datetime | None = None) -> str:
    """Return YYYY-MM in the digest timezone."""
    when = dt or _utc_now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local = when.astimezone(digest_timezone())
    return f"{local.year:04d}-{local.month:02d}"


def previous_month_key(dt: datetime | None = None) -> str:
    when = dt or _utc_now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local = when.astimezone(digest_timezone())
    year = local.year
    month = local.month - 1
    if month < 1:
        month = 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def period_label_for_month_key(month_key: str) -> str:
    """Human label like ``November 2026`` from ``YYYY-MM``."""
    try:
        year_s, month_s = month_key.split("-", 1)
        year = int(year_s)
        month = int(month_s)
        label = datetime(year, month, 1).strftime("%B %Y")
        return label
    except (TypeError, ValueError):
        return month_key


def archive_event(event: dict[str, Any]) -> bool:
    """Append an event for its queue month. Returns True when newly archived."""
    key = str(event.get("key") or "").strip()
    if not key:
        raise ValueError("monthly archive event requires key")
    queued_at = str(event.get("queued_at") or "").strip()
    month = str(event.get("month") or "").strip()
    if not month:
        if queued_at:
            try:
                parsed = datetime.fromisoformat(queued_at.replace("Z", "+00:00"))
                month = month_key_for(parsed)
            except ValueError:
                month = month_key_for()
        else:
            month = month_key_for()

    path = monthly_archive_path()
    with _lock:
        data = _load(path)
        existing = {str(e.get("key") or "") for e in data["events"]}
        if key in existing:
            return False
        payload = dict(event)
        payload["key"] = key
        payload["month"] = month
        payload.setdefault("queued_at", _utc_now_iso())
        data["events"].append(payload)
        _save(path, data)
    logger.info(
        "Archived monthly digest event key=%s month=%s kind=%s",
        key,
        month,
        event.get("kind"),
    )
    return True


def load_events_for_month(month_key: str) -> list[dict[str, Any]]:
    wanted = (month_key or "").strip()
    with _lock:
        events = list(_load(monthly_archive_path())["events"])
    return [e for e in events if str(e.get("month") or "") == wanted]


def remove_events_for_month(month_key: str) -> int:
    """Drop archived events for a finished month. Returns count removed."""
    wanted = (month_key or "").strip()
    if not wanted:
        return 0
    path = monthly_archive_path()
    with _lock:
        data = _load(path)
        before = len(data["events"])
        data["events"] = [
            e for e in data["events"] if str(e.get("month") or "") != wanted
        ]
        removed = before - len(data["events"])
        _save(path, data)
    return removed


def reset_monthly_archive_for_tests(path: Path | None = None) -> None:
    target = path or monthly_archive_path()
    with _lock:
        if target.exists():
            target.unlink()
        sibling = target.with_suffix(target.suffix + ".tmp")
        if sibling.exists():
            sibling.unlink()
