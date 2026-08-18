from unittest.mock import MagicMock, patch

import pytest

from api_client import APIClient
from legiscan_cache import LegiScanCache
from legiscan_processor import (
    LegiScanProcessor,
    normalize_bill_number,
    parse_legiscan_bill_url,
)


class FakeApi:
    def __init__(
        self,
        sessions=None,
        masterlists=None,
        search_results=None,
        text_docs=None,
    ):
        self.sessions = sessions or {}
        self.masterlists = masterlists or {}
        self.search_results = search_results or {}
        self.text_docs = text_docs or {}
        self._session_list_calls = 0

    def get_api_key(self):
        return "test-key"

    def get_session_list(self, state):
        self._session_list_calls += 1
        return {"sessions": self.sessions.get(state, [])}

    def get_master_list(self, session_id):
        return {"masterlist": self._lookup(self.masterlists, session_id)}

    @staticmethod
    def _lookup(store: dict, session_id) -> dict:
        if session_id in store:
            return store[session_id]
        try:
            alt = int(session_id)
            if alt in store:
                return store[alt]
        except (TypeError, ValueError):
            pass
        return {}

    def get_search_raw(self, query, state="ALL", year=2, page=1, session_id=None):
        key = (state, year, query)
        return self.search_results.get(key, {"status": "ERROR"})

    def get_bill_text_doc(self, doc_id):
        return self.text_docs.get(str(doc_id))


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_parse_legiscan_bill_url_bill_and_text_paths():
    assert parse_legiscan_bill_url("https://legiscan.com/NM/bill/SJM2/2024") == ("NM", "SJM2", 2024)
    assert parse_legiscan_bill_url("https://legiscan.com/UT/text/HB0480/2024") == ("UT", "HB0480", 2024)


def test_normalize_bill_number():
    assert normalize_bill_number("HB0015") == "HB15"
    assert normalize_bill_number("H.B. 116") == "HB116"


def test_resolve_bill_id_from_text_doc_url():
    api = FakeApi(text_docs={"2349651": {"bill_id": 111, "doc_id": 2349651}})
    proc = LegiScanProcessor(indigenous_db=None, api_client=api)
    bill_id = proc.resolve_bill_id(
        "https://legiscan.com/MT/text/HB35/id/2349651/Montana-2021-HB35-Enrolled.pdf"
    )
    assert bill_id == "111"


def test_resolve_bill_id_does_not_use_text_doc_id_as_bill_id_for_getbill():
    api = FakeApi(text_docs={"2349651": {"bill_id": 111, "doc_id": 2349651}})
    proc = LegiScanProcessor(indigenous_db=None, api_client=api)
    assert proc.resolve_bill_id(
        "https://legiscan.com/MT/text/HB35/id/2349651/Montana-2021-HB35-Enrolled.pdf"
    ) != "2349651"


def test_get_latest_bill_id_caches_session_list(tmp_path):
    client = APIClient("test-key", cache=LegiScanCache(tmp_path / "cache.db"))
    payload = {
        "status": "OK",
        "sessions": [{"session_id": 1, "year_start": 2024, "year_end": 2024}],
    }
    master_payload = {
        "status": "OK",
        "masterlist": {"0": {"number": "SJM2", "bill_id": 42}},
    }

    def fake_get(url, params=None, timeout=60):
        if "op=getSessionList" in url:
            return FakeResponse(200, payload)
        if "op=getMasterList" in url:
            return FakeResponse(200, master_payload)
        return FakeResponse(500, {})

    proc = LegiScanProcessor(indigenous_db=None, api_client=client)
    with patch("api_client.requests.get", side_effect=fake_get) as mock_get:
        assert proc.get_latest_bill_id("NM", 2024, "SJM2") == 42
        assert proc.get_latest_bill_id("NM", 2024, "SJM2") == 42
        session_calls = [c for c in mock_get.call_args_list if "op=getSessionList" in c.args[0]]
        assert len(session_calls) == 1


def test_get_latest_bill_id_tries_all_matching_sessions():
    api = FakeApi(
        sessions={
            "NM": [
                {"session_id": 1, "year_start": 2024, "year_end": 2024},
                {"session_id": 2, "year_start": 2024, "year_end": 2024},
            ]
        },
        masterlists={
            1: {"0": {"number": "HB1", "bill_id": 1}},
            2: {"0": {"number": "SJM2", "bill_id": 42}},
        },
    )
    proc = LegiScanProcessor(indigenous_db=None, api_client=api)
    assert proc.get_latest_bill_id("NM", 2024, "SJM2") == 42


def test_normalize_bill_number_in_master_list_lookup():
    api = FakeApi(
        sessions={"UT": [{"session_id": 1, "year_start": 2025, "year_end": 2025}]},
        masterlists={1: {"0": {"number": "HB15", "bill_id": 999}}},
    )
    proc = LegiScanProcessor(indigenous_db=None, api_client=api)
    assert proc.get_latest_bill_id("UT", 2025, "HB0015") == 999


def test_search_bill_id_fallback():
    api = FakeApi(
        search_results={
            ("CO", 2025, "HB1036"): {
                "status": "OK",
                "searchresult": {
                    "summary": {},
                    "0": {"bill_number": "HB1036", "bill_id": 5555},
                },
            }
        }
    )
    proc = LegiScanProcessor(indigenous_db=None, api_client=api)
    assert proc.search_bill_id("CO", "HB1036", 2025) == "5555"


def test_resolve_bill_id_text_path_without_doc_id():
    api = FakeApi(
        sessions={"UT": [{"session_id": 9, "year_start": 2024, "year_end": 2024}]},
        masterlists={9: {"0": {"number": "HB480", "bill_id": 8080}}},
    )
    proc = LegiScanProcessor(indigenous_db=None, api_client=api)
    assert proc.resolve_bill_id("https://legiscan.com/UT/text/HB0480/2024") == "8080"


def test_get_legiscan_text_error_returns_three_values():
    api = FakeApi(sessions={"XX": []})
    proc = LegiScanProcessor(indigenous_db=None, api_client=api)
    text, bill_id, doc_id = proc.get_legiscan_text(
        "https://legiscan.com/XX/bill/FAKE99/2099",
        document_processor=None,
    )
    assert bill_id is None
    assert doc_id is None
    assert "Invalid" in text


def _bill_details(
    *,
    completed: int = 0,
    status: int = 4,
    history: list | None = None,
    year_end: int = 2026,
) -> dict:
    return {
        "bill": {
            "completed": completed,
            "status": status,
            "bill_number": "SJR51",
            "history": history or [],
            "session": {"year_end": year_end},
        }
    }


def test_check_bill_status_completed_resolution_failed_to_adopt():
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    details = _bill_details(
        completed=1,
        status=4,
        history=[{"action": "Failed to adopt", "date": "2024-03-15", "chamber": "S"}],
    )
    assert proc.check_bill_status(details) == "Failed"


def test_check_bill_status_completed_with_failed_status_code():
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    details = _bill_details(completed=1, status=6)
    assert proc.check_bill_status(details) == "Failed"


def test_check_bill_status_completed_passed_bill():
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    details = _bill_details(
        completed=1,
        status=4,
        history=[{"action": "Signed by Governor", "date": "2024-06-01", "chamber": "A"}],
    )
    assert proc.check_bill_status(details) == "Passed"
