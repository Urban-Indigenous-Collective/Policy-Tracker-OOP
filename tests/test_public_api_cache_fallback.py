"""Public API keeps serving the last good Live data when Airtable is rate/billing limited."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import public_api.cache as cache

BILLING_LIMIT = Exception(
    "429 Client Error: PUBLIC_API_BILLING_LIMIT_EXCEEDED API billing plan limit exceeded"
)


def _record(rec_id: str, state: str = "NM") -> dict:
    return {"id": rec_id, "createdTime": "2026-01-01T00:00:00.000Z", "fields": {"State": state, "Name": rec_id}}


def _light_build(records, *, main_v3_count=None, policy_data_as_of=None):
    return cache.PublicSnapshot(
        records=list(records),
        bills=[],
        by_id={},
        by_state={},
        summary={},
        states={},
        map_layers={},
        generated_at=datetime.now(timezone.utc),
        live_count=len(records),
        main_v3_count=main_v3_count if main_v3_count is not None else len(records),
        policy_data_as_of=policy_data_as_of,
    )


class FakeClient:
    calls = 0
    init_kwargs: list[dict] = []
    behavior: object = None

    def __init__(self, **kwargs):
        FakeClient.init_kwargs.append(kwargs)

    def all_live_records(self):
        FakeClient.calls += 1
        if isinstance(FakeClient.behavior, Exception):
            raise FakeClient.behavior
        return FakeClient.behavior


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_API_SNAPSHOT_PATH", str(tmp_path / "public_api_snapshot.json"))
    monkeypatch.setattr(cache, "AirtableClient", FakeClient)
    monkeypatch.setattr(cache, "_build_snapshot", _light_build)
    monkeypatch.setattr(cache, "last_successful_status_refresh_at", lambda: None)
    FakeClient.calls = 0
    FakeClient.init_kwargs = []
    FakeClient.behavior = None
    cache.reset_cache_for_tests()
    yield
    cache.reset_cache_for_tests()


def test_successful_fetch_persists_records(tmp_path):
    FakeClient.behavior = [_record("rec1"), _record("rec2")]

    snap = cache.get_snapshot()

    assert snap.live_count == 2 and not snap.stale
    saved = json.loads((tmp_path / "public_api_snapshot.json").read_text())
    assert saved["record_count"] == 2
    assert [r["id"] for r in saved["records"]] == ["rec1", "rec2"]


def test_fetch_fails_fast_with_limited_retries(monkeypatch):
    FakeClient.behavior = [_record("rec1")]
    cache.get_snapshot()
    assert FakeClient.init_kwargs[-1] == {"retry_total": 1}

    monkeypatch.setenv("PUBLIC_API_AIRTABLE_RETRY_TOTAL", "0")
    cache.get_snapshot(force=True)
    assert FakeClient.init_kwargs[-1] == {"retry_total": 0}


def test_billing_limit_after_restart_serves_persisted_snapshot():
    FakeClient.behavior = [_record("rec1"), _record("rec2"), _record("rec3")]
    cache.get_snapshot()
    cache.reset_cache_for_tests()  # simulate web container restart (memory wiped)

    FakeClient.behavior = BILLING_LIMIT
    snap = cache.get_snapshot()

    assert snap.live_count == 3
    assert snap.stale is True
    assert snap.upstream_error == "airtable_limit"


def test_billing_limit_with_memory_snapshot_serves_it_stale(monkeypatch):
    FakeClient.behavior = [_record("rec1")]
    first = cache.get_snapshot()

    FakeClient.behavior = BILLING_LIMIT
    again = cache.get_snapshot(force=True)

    assert again is first
    assert again.stale is True and again.upstream_error == "airtable_limit"


def test_failed_refresh_backs_off_instead_of_hitting_airtable_every_request():
    FakeClient.behavior = [_record("rec1")]
    cache.get_snapshot()
    cache.reset_cache_for_tests()

    FakeClient.behavior = BILLING_LIMIT
    cache.get_snapshot()
    calls_after_failure = FakeClient.calls
    for _ in range(5):
        cache.get_snapshot()

    assert FakeClient.calls == calls_after_failure


def test_no_persisted_snapshot_raises_upstream_unavailable():
    FakeClient.behavior = BILLING_LIMIT
    with pytest.raises(cache.UpstreamUnavailableError, match="rate limit"):
        cache.get_snapshot()


def test_stale_on_error_disabled_raises(monkeypatch):
    FakeClient.behavior = [_record("rec1")]
    cache.get_snapshot()
    cache.reset_cache_for_tests()
    monkeypatch.setenv("PUBLIC_API_STALE_ON_ERROR", "0")

    FakeClient.behavior = BILLING_LIMIT
    with pytest.raises(cache.UpstreamUnavailableError):
        cache.get_snapshot()


def test_loads_combined_live_dump_and_keeps_its_timestamp(tmp_path):
    (tmp_path / "public_api_snapshot.json").write_text(
        json.dumps(
            {
                "taken_at": "20261119T161547Z",
                "live": [_record("a"), _record("b")],
                "pending": [_record("p")],
            }
        )
    )
    FakeClient.behavior = BILLING_LIMIT

    snap = cache.get_snapshot()

    assert snap.live_count == 2
    assert snap.generated_at == datetime(2026, 11, 19, 16, 15, 47, tzinfo=timezone.utc)


def test_corrupt_persisted_snapshot_is_ignored(tmp_path):
    (tmp_path / "public_api_snapshot.json").write_text("{not json")
    FakeClient.behavior = BILLING_LIMIT
    with pytest.raises(cache.UpstreamUnavailableError):
        cache.get_snapshot()


def test_health_reports_stale_upstream(monkeypatch):
    from app import app

    FakeClient.behavior = [_record("rec1")]
    cache.get_snapshot()
    cache.reset_cache_for_tests()
    FakeClient.behavior = BILLING_LIMIT

    response = app.test_client().get("/api/v1/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["stale"] is True
    assert body["upstreamError"] == "airtable_limit"
