"""In-memory snapshot of public Live Main v3 data (Airtable throttle)."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from airtable_client import AirtableClient, is_airtable_rate_limit_error
from public_api.gate import filter_public_live_records
from public_api.map_aggregate import build_states_payload
from public_api.serialize import record_to_bill_dto
from public_api.policy_freshness import last_successful_status_refresh_at
from public_api.states import normalize_public_state

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_snapshot: "PublicSnapshot | None" = None


def cache_ttl_seconds() -> int:
    return max(30, int(os.getenv("PUBLIC_API_CACHE_TTL_SECONDS", "300")))


def stale_on_error() -> bool:
    return os.getenv("PUBLIC_API_STALE_ON_ERROR", "1").lower() in ("1", "true", "yes")


@dataclass
class PublicSnapshot:
    records: list[dict[str, Any]]
    bills: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]]
    by_state: dict[str, list[dict[str, Any]]]
    summary: dict[str, int]
    states: dict[str, dict[str, Any]]
    generated_at: datetime
    live_count: int = field(default=0)
    main_v3_count: int = field(default=0)
    policy_data_as_of: datetime | None = field(default=None)

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
    return PublicSnapshot(
        records=live,
        bills=bills,
        by_id=by_id,
        by_state=by_state,
        summary=summary,
        states=states,
        generated_at=datetime.now(timezone.utc),
        live_count=len(live),
        main_v3_count=main_v3_count if main_v3_count is not None else len(records),
        policy_data_as_of=policy_data_as_of,
    )


def _fetch_from_airtable() -> PublicSnapshot:
    client = AirtableClient()
    started = time.monotonic()
    raw = client.all_live_records()
    snapshot = _build_snapshot(
        raw,
        main_v3_count=len(raw),
        policy_data_as_of=last_successful_status_refresh_at(),
    )
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
    global _snapshot
    ttl = cache_ttl_seconds()

    with _lock:
        if not force and _snapshot is not None and _snapshot.cache_age_seconds < ttl:
            return _snapshot
        try:
            _snapshot = _fetch_from_airtable()
            return _snapshot
        except Exception as exc:
            if _snapshot is not None and stale_on_error():
                logger.warning("public_api cache refresh failed, serving stale: %s", exc)
                return _snapshot
            if is_airtable_rate_limit_error(exc):
                raise UpstreamUnavailableError("Airtable rate limit") from exc
            raise UpstreamUnavailableError(str(exc)) from exc


def reset_cache_for_tests() -> None:
    global _snapshot
    with _lock:
        _snapshot = None
