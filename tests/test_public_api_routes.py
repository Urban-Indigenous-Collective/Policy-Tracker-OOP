"""Flask route tests for /api/v1 with mocked snapshot cache."""

from datetime import datetime, timezone

import pytest

from airtable_fields import LIVE_REVIEW_STATUS_FIELD, REVIEW_STATUS_LIVE
from public_api.cache import PublicSnapshot, reset_cache_for_tests


@pytest.fixture(autouse=True)
def clear_cache():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def _sample_snapshot():
    records = [
        {
            "id": "recWA001",
            "fields": {
                "Name": "WA Act",
                "State": "WA",
                "Status": "Passed",
                "Bill Number": "SB 1",
                "Session": "2023",
                LIVE_REVIEW_STATUS_FIELD: REVIEW_STATUS_LIVE,
            },
        }
    ]
    from public_api.cache import _build_snapshot

    return _build_snapshot(records)


def test_states_endpoint(client, monkeypatch):
    snap = _sample_snapshot()
    monkeypatch.setattr("public_api.routes.get_snapshot", lambda **_: snap)

    resp = client.get("/api/v1/states")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["summary"]["passed"] == 1
    assert data["states"]["WA"]["category"] == "passed"
    assert "generatedAt" in data


def test_state_bills_endpoint(client, monkeypatch):
    snap = _sample_snapshot()
    monkeypatch.setattr("public_api.routes.get_snapshot", lambda **_: snap)

    resp = client.get("/api/v1/states/WA/bills")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["state"] == "WA"
    assert len(data["bills"]) == 1
    assert data["bills"][0]["name"] == "WA Act"


def test_state_bills_not_found(client, monkeypatch):
    snap = _sample_snapshot()
    monkeypatch.setattr("public_api.routes.get_snapshot", lambda **_: snap)

    resp = client.get("/api/v1/states/ZZ/bills")
    assert resp.status_code == 404


def test_bill_detail(client, monkeypatch):
    snap = _sample_snapshot()
    monkeypatch.setattr("public_api.routes.get_snapshot", lambda **_: snap)

    resp = client.get("/api/v1/bills/recWA001")
    assert resp.status_code == 200
    assert resp.get_json()["bill"]["id"] == "recWA001"


@pytest.fixture
def client():
    from app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
