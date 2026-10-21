"""Unit tests for public API gate, serialize, and map aggregation."""

import pytest

from airtable_fields import LIVE_REVIEW_STATUS_FIELD, REVIEW_STATUS_LIVE
from public_api.gate import filter_public_live_records, is_public_live_record
from public_api.map_aggregate import (
    build_summary_stats,
    state_legend_category,
)
from public_api.serialize import bill_slug, record_to_bill_dto


def _record(rid: str, **fields):
    return {"id": rid, "fields": fields}


def test_gate_requires_live_by_default(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_REQUIRE_LIVE", "1")
    live = _record("rec1", **{LIVE_REVIEW_STATUS_FIELD: REVIEW_STATUS_LIVE, "State": "WA"})
    pending = _record("rec2", **{LIVE_REVIEW_STATUS_FIELD: "Send Back to Pending"})
    assert is_public_live_record(live)
    assert not is_public_live_record(pending)
    assert len(filter_public_live_records([live, pending])) == 1


def test_serialize_bill_dto():
    fields = {
        "Name": "Test Act",
        "State": "WA",
        "Status": "Passed",
        "Bill Number": "HB 100",
        "Session": "2024",
        "Bill Overview (Link)": "https://example.com/bill",
        LIVE_REVIEW_STATUS_FIELD: REVIEW_STATUS_LIVE,
    }
    rec = _record("recABCDEFGH", **fields)
    dto = record_to_bill_dto(rec)
    assert dto["name"] == "Test Act"
    assert dto["state"] == "WA"
    assert dto["slug"] == bill_slug("recABCDEFGH", rec["fields"])
    assert "hb-100-2024" in dto["slug"]


def test_summary_stats():
    bills = [
        {"status": "Passed"},
        {"status": "Pending"},
        {"status": "Failed"},
    ]
    assert build_summary_stats(bills) == {"passed": 1, "pending": 1, "rejected": 1}


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (["Passed"], "passed"),
        (["Passed", "Pending"], "passedAdditional"),
        (["Pending"], "pending"),
        (["Failed"], "failed"),
        (["Failed", "Pending"], "failedAdditional"),
        (["Pending", "Failed"], "failedAdditional"),
    ],
)
def test_state_legend_category(statuses, expected):
    bills = [{"status": s} for s in statuses]
    assert state_legend_category(bills) == expected


def test_build_states_payload_excludes_national():
    from public_api.map_aggregate import build_states_payload

    records = [
        _record(
            "rec1",
            State="National",
            Status="Passed",
            Name="EO",
            **{LIVE_REVIEW_STATUS_FIELD: REVIEW_STATUS_LIVE},
        ),
        _record(
            "rec2",
            State="WA",
            Status="Passed",
            Name="WA Bill",
            **{LIVE_REVIEW_STATUS_FIELD: REVIEW_STATUS_LIVE},
        ),
    ]
    summary, states = build_states_payload(records)
    assert summary["passed"] == 2
    assert "WA" in states
    assert "National" not in states
