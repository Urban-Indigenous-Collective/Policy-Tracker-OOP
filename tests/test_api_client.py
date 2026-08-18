"""Tests for LegiScan APIClient caching, budget, and error handling."""

from unittest.mock import MagicMock, patch

import pytest

from api_client import (
    APIClient,
    LegiScanBudgetExceededError,
    LegiScanDisabledError,
    LegiScanOverlimitError,
)
from legiscan_cache import LegiScanCache


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


@pytest.fixture
def cache(tmp_path):
    return LegiScanCache(tmp_path / "legiscan_api_cache.db")


def test_session_list_sqlite_cache(cache):
    client = APIClient("test-key", cache=cache)
    payload = {"status": "OK", "sessions": [{"session_id": 1, "year_start": 2025}]}

    with patch("api_client.requests.get", return_value=FakeResponse(200, payload)) as mock_get:
        first = client.get_session_list("NM")
        client._memory_cache.clear()
        second = client.get_session_list("NM")

    assert first == payload
    assert second == payload
    assert mock_get.call_count == 1
    assert client.stats.network == 1
    assert client.stats.sqlite_cache_hit == 1


def test_get_bill_not_sqlite_cached(cache):
    client = APIClient("test-key", cache=cache)
    payload = {"status": "OK", "bill": {"bill_id": 1}}

    with patch("api_client.requests.get", return_value=FakeResponse(200, payload)) as mock_get:
        client.get_bill_details(1)
        client.get_bill_details(1)

    assert mock_get.call_count == 1
    assert client.stats.memory_cache_hit == 1


def test_overlimit_raises_without_retry(cache):
    client = APIClient("test-key", cache=cache)
    payload = {"status": "ERROR", "alert": "monthly query limit exceeded"}

    with patch("api_client.requests.get", return_value=FakeResponse(200, payload)) as mock_get:
        with pytest.raises(LegiScanOverlimitError):
            client.get_bill_details(99)

    assert mock_get.call_count == 1


def test_network_budget_enforced(cache, monkeypatch):
    monkeypatch.setenv("LEGISCAN_MAX_NETWORK_QUERIES_PER_JOB", "1")
    client = APIClient("test-key", cache=cache)
    payload = {"status": "OK", "bill": {"bill_id": 1}}

    with patch("api_client.requests.get", return_value=FakeResponse(200, payload)):
        client.get_bill_details(1)
        with pytest.raises(LegiScanBudgetExceededError):
            client.get_bill_details(2)


def test_api_disabled(cache, monkeypatch):
    monkeypatch.setenv("LEGISCAN_API_ENABLED", "false")
    client = APIClient("test-key", cache=cache)
    with pytest.raises(LegiScanDisabledError):
        client.get_bill_details(1)


def test_log_stats(cache, caplog):
    client = APIClient("test-key", cache=cache)
    with caplog.at_level("INFO"):
        client.log_stats()
    assert "legiscan_ops" in caplog.text
