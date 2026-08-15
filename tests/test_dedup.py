"""Tests for Airtable duplicate index."""

from discovery.dedup import AirtableDuplicateIndex
from discovery.url_utils import normalize_url


class FakeTable:
    def __init__(self, records):
        self.records = records

    def all(self):
        return self.records


class FakeAirtable:
    def __init__(self, live_records, pending_records):
        self.live_table = FakeTable(live_records)
        self.pending_table = FakeTable(pending_records)


def test_duplicate_by_normalized_url():
    client = FakeAirtable(
        live_records=[
            {
                "fields": {
                    "State": "NM",
                    "Bill Number": "SB12",
                    "Bill Overview (Link)": "https://www.legiscan.com/NM/bill/SB12/2022/",
                }
            }
        ],
        pending_records=[],
    )
    index = AirtableDuplicateIndex(client)
    assert index.is_duplicate("https://legiscan.com/NM/bill/SB12/2022")
    assert not index.is_duplicate("https://legiscan.com/NM/bill/SB99/2022")


def test_duplicate_by_state_and_bill_number():
    client = FakeAirtable(
        live_records=[
            {
                "fields": {
                    "State": "WA",
                    "Bill Number": "HB 1177",
                    "Bill Overview (Link)": "https://app.leg.wa.gov/billsummary?BillNumber=1177",
                }
            }
        ],
        pending_records=[],
    )
    index = AirtableDuplicateIndex(client)
    # Same bill, different URL (LegiScan vs state site)
    assert index.is_duplicate(
        "https://legiscan.com/WA/bill/HB1177/2023",
        state="WA",
        bill_number="HB1177",
    )


def test_register_tracks_within_run():
    client = FakeAirtable(live_records=[], pending_records=[])
    index = AirtableDuplicateIndex(client)
    index.refresh()
    assert not index.is_duplicate("https://example.com/bill/1", state="NM", bill_number="SB1")
    index.register(
        url="https://example.com/bill/1",
        state="NM",
        bill_number="SB1",
    )
    assert index.is_duplicate("https://example.com/bill/1", state="NM", bill_number="SB1")


def test_duplicate_federal_doj_url_in_main_without_bill_id():
    """Federal/DOJ items without bill numbers dedupe by normalized URL in Main v3."""
    doj_url = (
        "https://www.justice.gov/usao-wdmi/pr/2020_1218_MMIP"
    )
    client = FakeAirtable(
        live_records=[
            {
                "fields": {
                    "State": "MI",
                    "Name": "U.S. Attorney General's MMIP Initiative",
                    "Bill Overview (Link)": doj_url,
                }
            }
        ],
        pending_records=[],
    )
    index = AirtableDuplicateIndex(client)
    assert index.is_duplicate(doj_url)
    assert index.is_duplicate("http://justice.gov/usao-wdmi/pr/2020_1218_MMIP")
    assert not index.is_duplicate(
        "https://justice.gov/usao-wdmi/pr/2024_0506_MMIP_March"
    )


def test_duplicate_doj_archives_opa_matches_live_opa_path():
    live_url = "https://www.justice.gov/opa/pr/fact-sheet-mmip"
    archives_url = "https://www.justice.gov/archives/opa/pr/fact-sheet-mmip"
    client = FakeAirtable(
        live_records=[
            {
                "fields": {
                    "State": "National",
                    "Name": "DOJ fact sheet",
                    "Bill Overview (Link)": live_url,
                }
            }
        ],
        pending_records=[],
    )
    index = AirtableDuplicateIndex(client)
    assert index.is_duplicate(archives_url)
    assert normalize_url(live_url) == normalize_url(archives_url)


def test_duplicate_federal_url_in_bill_text_field():
    client = FakeAirtable(
        live_records=[
            {
                "fields": {
                    "State": "AK",
                    "Bill Text": (
                        "https://www.justice.gov/usao-ak/pr/"
                        "pilot-projects-launched-address-missing-and-murdered-indigenous-persons"
                    ),
                }
            }
        ],
        pending_records=[],
    )
    index = AirtableDuplicateIndex(client)
    assert index.is_duplicate(
        "https://justice.gov/usao-ak/pr/pilot-projects-launched-address-missing-and-murdered-indigenous-persons"
    )
