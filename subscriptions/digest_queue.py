"""Overnight queue of Live bill events for morning subscriber digests."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.RLock()

DIGEST_KIND_NEW_LIVE = "new_live"
DIGEST_KIND_STATUS = "status"
EMAIL_STATUS_FIELDS = frozenset({"Status", "Progression"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest_queue_path() -> Path:
    override = (os.getenv("STATE_SUBSCRIBE_DIGEST_QUEUE_PATH") or "").strip()
    if override:
        return Path(override)
    db_path = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
    return db_path.parent / "pending_subscriber_digest.json"


def _empty_queue() -> dict[str, Any]:
    return {"events": []}


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_queue()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("subscriber digest queue unreadable (%s); starting empty", exc)
        return _empty_queue()
    if not isinstance(data, dict):
        return _empty_queue()
    events = data.get("events")
    if not isinstance(events, list):
        events = []
    return {"events": events}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def event_key(
    *,
    kind: str,
    record_id: str = "",
    url: str = "",
    fingerprint: str = "",
) -> str:
    anchor = (record_id or url or "unknown").strip()
    fp = (fingerprint or kind).strip()
    return f"{anchor}|{kind}|{fp}"


def status_fingerprint(changes: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for change in changes:
        field = str(change.get("field") or "")
        if field not in EMAIL_STATUS_FIELDS:
            continue
        parts.append(f"{field}={change.get('new') or ''}")
    return "|".join(sorted(parts))


def enqueue_event(event: dict[str, Any]) -> bool:
    """Append an event if its key is new. Returns True when queued."""
    key = str(event.get("key") or "").strip()
    if not key:
        raise ValueError("digest event requires key")
    path = digest_queue_path()
    with _lock:
        data = _load(path)
        existing = {str(e.get("key") or "") for e in data["events"]}
        if key in existing:
            return False
        payload = dict(event)
        payload["key"] = key
        payload.setdefault("queued_at", _utc_now_iso())
        data["events"].append(payload)
        _save(path, data)
    logger.info("Queued subscriber digest event key=%s kind=%s", key, event.get("kind"))
    return True


def enqueue_new_live(
    *,
    state: str,
    title: str,
    url: str,
    record_id: str = "",
    public_path: str = "",
) -> bool:
    key = event_key(
        kind=DIGEST_KIND_NEW_LIVE,
        record_id=record_id,
        url=url,
        fingerprint=DIGEST_KIND_NEW_LIVE,
    )
    return enqueue_event(
        {
            "key": key,
            "kind": DIGEST_KIND_NEW_LIVE,
            "state": state,
            "title": title,
            "url": url,
            "record_id": record_id,
            "public_path": public_path,
            "summary": "New on the tracker",
        }
    )


def enqueue_live_status_changes(
    *,
    state: str,
    title: str,
    url: str,
    changes: list[dict[str, str]],
    record_id: str = "",
    public_path: str = "",
) -> bool:
    meaningful = [c for c in changes if str(c.get("field") or "") in EMAIL_STATUS_FIELDS]
    if not meaningful:
        return False
    fp = status_fingerprint(meaningful)
    key = event_key(
        kind=DIGEST_KIND_STATUS,
        record_id=record_id,
        url=url,
        fingerprint=fp,
    )
    summaries = [
        f"{c['field']}: {c.get('old') or '—'} → {c.get('new') or '—'}"
        for c in meaningful
    ]
    return enqueue_event(
        {
            "key": key,
            "kind": DIGEST_KIND_STATUS,
            "state": state,
            "title": title,
            "url": url,
            "record_id": record_id,
            "public_path": public_path,
            "summary": "; ".join(summaries),
            "changes": meaningful,
        }
    )


def load_events() -> list[dict[str, Any]]:
    with _lock:
        return list(_load(digest_queue_path())["events"])


def remove_events(keys: set[str] | list[str]) -> int:
    """Remove queued events by key. Returns count removed."""
    wanted = {str(k) for k in keys if k}
    if not wanted:
        return 0
    path = digest_queue_path()
    with _lock:
        data = _load(path)
        before = len(data["events"])
        data["events"] = [
            e for e in data["events"] if str(e.get("key") or "") not in wanted
        ]
        removed = before - len(data["events"])
        _save(path, data)
    return removed


def clear_queue() -> None:
    path = digest_queue_path()
    with _lock:
        _save(path, _empty_queue())


def reset_digest_queue_for_tests(path: Path | None = None) -> None:
    target = path or digest_queue_path()
    with _lock:
        if target.exists():
            target.unlink()
        sibling = target.with_suffix(target.suffix + ".tmp")
        if sibling.exists():
            sibling.unlink()
