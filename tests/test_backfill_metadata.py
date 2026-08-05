"""Tests for metadata backfill helpers."""

import datetime as dt

from scripts.backfill_metadata import PRESIDENTIAL_TERMS, administration_from_date


def test_administration_from_date_obama_term():
    assert administration_from_date("2010-10-20") == "Obama Administration"


def test_administration_from_date_trump_first_term():
    assert administration_from_date("2019-11-26") == "Trump Administration"


def test_administration_from_date_biden_term():
    assert administration_from_date("2024-05-27") == "Biden Administration"
    assert administration_from_date("2022-05-05") == "Biden Administration"


def test_administration_from_date_trump_second_term():
    assert administration_from_date("2026-05-04") == "Trump Administration"


def test_administration_from_date_empty_or_invalid():
    assert administration_from_date("") == ""
    assert administration_from_date("not-a-date") == ""


def test_presidential_terms_cover_inauguration_boundaries():
    # Biden term starts inauguration day; prior day is still Trump (first term).
    assert administration_from_date("2021-01-19") == "Trump Administration"
    assert administration_from_date("2021-01-20") == "Biden Administration"
    assert administration_from_date("2025-01-19") == "Biden Administration"
    assert administration_from_date("2025-01-20") == "Trump Administration"


def test_presidential_terms_table_has_four_entries():
    assert len(PRESIDENTIAL_TERMS) == 4


def test_federal_session_update_infers_source_from_justice_gov_url():
    from scripts.backfill_metadata import _federal_session_update

    fields = {
        "Last Update": "2023-09-20",
        "Bill Overview (Link)": "https://www.justice.gov/usao-ak/pr/example",
    }
    updates = _federal_session_update(fields, {}, fields["Bill Overview (Link)"])
    assert updates == {"Session": "Biden Administration"}

