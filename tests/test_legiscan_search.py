from unittest.mock import MagicMock

from discovery.legiscan_search import LegiScanSearchSource


class FakeAPIClient:
    def __init__(self, pages, bills=None):
        self.pages = pages
        self.bills = bills or {}
        self.get_bill_details = MagicMock(
            side_effect=lambda bill_id: self._get_bill_details(bill_id)
        )

    def _get_bill_details(self, bill_id):
        bid = str(bill_id)
        if bid in self.bills:
            return {"status": "OK", "bill": self.bills[bid]}
        return {"status": "OK", "bill": {
            "state": "NM",
            "url": f"https://legiscan.com/NM/bill/SB{bid}/2025",
            "title": f"Bill {bid}",
            "history": [{"action": "Introduced"}],
        }}

    def iter_search_raw_pages(self, query, state="ALL", year=2, max_pages=None):
        yield from self.pages


SAMPLE_SEARCH_RESPONSE = {
    "status": "OK",
    "searchresult": {
        "summary": {"page_total": 1},
        "results": [
            {
                "bill_id": 12345,
                "state": "NM",
                "url": "https://legiscan.com/NM/bill/SB123/2025",
                "title": "Missing and Murdered Indigenous Persons Task Force",
                "last_action": "Passed Senate",
                "change_hash": "hash1",
                "relevance": 95,
            },
            {
                "bill_id": 12345,
                "state": "NM",
                "url": "https://legiscan.com/NM/bill/SB123/2025",
                "title": "Duplicate bill",
                "change_hash": "hash1",
                "relevance": 95,
            },
            {
                "bill_id": 67890,
                "state": "IA",
                "url": "https://legiscan.com/IA/bill/HF456/2025",
                "title": "AMBER Alert Expansion",
                "change_hash": "hash2",
                "relevance": 40,
            },
        ],
    },
}


def test_legiscan_search_dedupes_bill_ids():
    source = LegiScanSearchSource(FakeAPIClient([SAMPLE_SEARCH_RESPONSE]))
    candidates = list(source.discover(queries=['MMIP']))
    assert len(candidates) == 2
    assert candidates[0].external_id == "12345"
    assert candidates[0].state == "NM"
    assert candidates[1].external_id == "67890"
    source.api.get_bill_details.assert_not_called()


def test_legiscan_search_uses_search_fields_without_hydration():
    source = LegiScanSearchSource(FakeAPIClient([SAMPLE_SEARCH_RESPONSE]))
    candidates = list(source.discover(queries=["MMIP"]))
    assert candidates[0].title == "Missing and Murdered Indigenous Persons Task Force"
    assert candidates[0].snippet == "Passed Senate"
    source.api.get_bill_details.assert_not_called()


def test_legiscan_search_handles_dict_results():
    page = {
        "status": "OK",
        "searchresult": {
            "summary": {"page_total": 1},
            "results": {
                "0": {
                    "bill_id": 111,
                    "state": "AK",
                    "url": "https://legiscan.com/AK/bill/SB1/2025",
                    "title": "MMIP data collection",
                    "change_hash": "x",
                    "relevance": 80,
                }
            },
        },
    }
    source = LegiScanSearchSource(FakeAPIClient([page]))
    candidates = list(source.discover(queries=["MMIP"]))
    assert len(candidates) == 1
    assert candidates[0].state == "AK"
