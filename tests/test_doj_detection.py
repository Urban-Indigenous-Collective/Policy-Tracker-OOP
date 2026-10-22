"""DOJ / USAO bill detection for map layers."""

from public_api.doj_detection import (
    is_doj_initiative_bill,
    is_doj_initiative_record,
    url_looks_doj_linked,
)


def test_url_looks_doj_linked_variants():
    assert url_looks_doj_linked("https://www.justice.gov/usao-ak/pr/mmip")
    assert url_looks_doj_linked("http://justice.gov/archives/opa/pr/fact-sheet-mmip")
    assert not url_looks_doj_linked("https://www.congress.gov/bill/123")


def test_doj_bill_from_optional_link():
    bill = {
        "name": "District plan",
        "billOverviewUrl": "",
        "optionalLink": "https://www.justice.gov/usao-or/pr/mmip-plan",
        "categories": [],
    }
    assert is_doj_initiative_bill(bill)


def test_us_law_enforcement_category_alone_is_not_doj():
    bill = {
        "name": "NJ MMIP task force act",
        "state": "NJ",
        "billOverviewUrl": "https://www.njleg.state.nj.us/bills/BillView.asp",
        "billNumber": "A 1234",
        "categories": ["US Law Enforcement"],
    }
    assert not is_doj_initiative_bill(bill)


def test_doj_bill_from_usao_name_without_url():
    bill = {
        "name": "USAO plan for MMIP outreach",
        "billOverviewUrl": "",
        "billNumber": "",
        "categories": [],
    }
    assert is_doj_initiative_bill(bill)


def test_doj_name_alone_with_bill_number_is_not_doj():
    bill = {
        "name": "DOJ oversight report",
        "billOverviewUrl": "https://example.com/report",
        "billNumber": "HB 100",
        "categories": [],
    }
    assert not is_doj_initiative_bill(bill)


def test_doj_record_pending_style_fields():
    record = {
        "fields": {
            "Title": "DOJ fact sheet",
            "Bill Overview": "https://www.justice.gov/opa/pr/mmip",
        }
    }
    assert is_doj_initiative_record(record)
