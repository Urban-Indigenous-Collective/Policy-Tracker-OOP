"""In-memory snapshot of public Live Main v3 data (Airtable throttle).

Every successful Airtable fetch is also written to disk. When Airtable fails (rate or
monthly billing limit, outage) the last good data is served from memory, or from that
file after a restart, so the public map never depends on Airtable being reachable.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from airtable_client import AirtableClient, is_airtable_rate_limit_error
from public_api.gate import filter_public_live_records
from public_api.map_aggregate import build_map_layers, build_states_payload
from public_api.serialize import record_to_bill_dto
from public_api.policy_freshness import last_successful_status_refresh_at
from public_api.states import normalize_public_state

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_snapshot: "PublicSnapshot | None" = None
_next_refresh_at = 0.0  # time.monotonic(); failed refreshes also wait a full TTL


def cache_ttl_seconds() -> int:
    return max(30, int(os.getenv("PUBLIC_API_CACHE_TTL_SECONDS", "300")))


def stale_on_error() -> bool:
    return os.getenv("PUBLIC_API_STALE_ON_ERROR", "1").lower() in ("1", "true", "yes")


def airtable_retry_total() -> int:
    # Requests block on this fetch; Airtable's default 6 backoff retries take ~2 minutes,
    # past nginx's 60s timeout. A billing-limit 429 never clears by retrying anyway.
    return max(0, int(os.getenv("PUBLIC_API_AIRTABLE_RETRY_TOTAL", "1")))


def snapshot_path() -> Path:
    override = os.getenv("PUBLIC_API_SNAPSHOT_PATH", "").strip()
    if override:
        return Path(override)
    return Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")).parent / "public_api_snapshot.json"


@dataclass
class PublicSnapshot:
    records: list[dict[str, Any]]
    bills: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]]
    by_state: dict[str, list[dict[str, Any]]]
    summary: dict[str, int]
    states: dict[str, dict[str, Any]]
    map_layers: dict[str, Any]
    generated_at: datetime
    live_count: int = field(default=0)
    main_v3_count: int = field(default=0)
    policy_data_as_of: datetime | None = field(default=None)
    stale: bool = field(default=False)
    upstream_error: str | None = field(default=None)

    @property
    def cache_age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.generated_at).total_seconds()


def _build_snapshot(
    records: list[dict[str, Any]],
    *,
    main_v3_count: int | None = None,
    policy_data_as_of: datetime | None = None,
) -> PublicSnapshot:
    live = filter_public_live_records(records)
    bills = [record_to_bill_dto(record) for record in live]
    by_id = {bill["id"]: bill for bill in bills if bill.get("id")}
    by_state: dict[str, list[dict[str, Any]]] = {}
    for bill in bills:
        code = normalize_public_state(bill.get("state"))
        bill["state"] = code
        by_state.setdefault(code, []).append(bill)

    summary, states = build_states_payload(live)
    map_layers = build_map_layers(bills)
    return PublicSnapshot(
        records=live,
        bills=bills,
        by_id=by_id,
        by_state=by_state,
        summary=summary,
        states=states,
        map_layers=map_layers,
        generated_at=datetime.now(timezone.utc),
        live_count=len(live),
        main_v3_count=main_v3_count if main_v3_count is not None else len(records),
        policy_data_as_of=policy_data_as_of,
    )


def _persist_records(raw: list[dict[str, Any]]) -> None:
    """Write the last good Live records to disk atomically. Never raises."""
    path = snapshot_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "table": "Main v3",
            "record_count": len(raw),
            "records": raw,
        }
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning("public_api could not persist snapshot to %s: %s", path, exc)


def _load_persisted() -> PublicSnapshot | None:
    """Rebuild a snapshot from the last persisted Live records, if any."""
    path = snapshot_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("records")
        if not isinstance(records, list):
            records = data.get("live")  # combined live/pending Airtable dump
        if not isinstance(records, list) or not records:
            return None
        snapshot = _build_snapshot(
            records,
            main_v3_count=len(records),
            policy_data_as_of=last_successful_status_refresh_at(),
        )
        exported = data.get("exported_at") or data.get("taken_at")
        if exported:
            try:
                parsed = datetime.fromisoformat(str(exported).replace("Z", "+00:00"))
            except ValueError:
                parsed = datetime.strptime(str(exported), "%Y%m%dT%H%M%SZ")
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            snapshot.generated_at = parsed
        logger.warning(
            "public_api loaded persisted snapshot: live=%s exported_at=%s path=%s",
            snapshot.live_count,
            exported,
            path,
        )
        return snapshot
    except Exception as exc:
        logger.warning("public_api could not load persisted snapshot %s: %s", path, exc)
        return None


def _fetch_from_airtable() -> PublicSnapshot:
    client = AirtableClient(retry_total=airtable_retry_total())
    started = time.monotonic()
    raw = client.all_live_records()
    snapshot = _build_snapshot(
        raw,
        main_v3_count=len(raw),
        policy_data_as_of=last_successful_status_refresh_at(),
    )
    _persist_records(raw)
    logger.info(
        "public_api cache refresh: live=%s raw=%s duration_ms=%.0f",
        snapshot.live_count,
        len(raw),
        (time.monotonic() - started) * 1000,
    )
    return snapshot


class UpstreamUnavailableError(Exception):
    pass


def get_snapshot(*, force: bool = False) -> PublicSnapshot:
    global _snapshot, _next_refresh_at
    ttl = cache_ttl_seconds()

    with _lock:
        if not force and _snapshot is not None and time.monotonic() < _next_refresh_at:
            return _snapshot
        try:
            _snapshot = _fetch_from_airtable()
            _next_refresh_at = time.monotonic() + ttl
            return _snapshot
        except Exception as exc:
            limited = is_airtable_rate_limit_error(exc)
            # Back off a full TTL so every request does not re-hit a failing Airtable.
            _next_refresh_at = time.monotonic() + ttl
            if stale_on_error():
                if _snapshot is None:
                    _snapshot = _load_persisted()
                if _snapshot is not None:
                    _snapshot.stale = True
                    _snapshot.upstream_error = "airtable_limit" if limited else type(exc).__name__
                    logger.warning("public_api cache refresh failed, serving stale: %s", exc)
                    return _snapshot
            if limited:
                raise UpstreamUnavailableError("Airtable rate limit") from exc
            raise UpstreamUnavailableError(str(exc)) from exc


def reset_cache_for_tests() -> None:
    global _snapshot, _next_refresh_at
    with _lock:
        _snapshot = None
        _next_refresh_at = 0.0
