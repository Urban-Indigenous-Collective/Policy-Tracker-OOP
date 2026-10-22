"""Map legend aggregation (all Live Main v3 rows per state)."""

from public_api.map_aggregate import build_states_payload, state_legend_category


def test_state_legend_uses_status_not_progression():
    bills = [{"status": "Failed", "progression": "Introduced", "billNumber": "SF1"}]
    assert state_legend_category(bills) == "failed"


def test_state_legend_pending_mixed_failed():
    bills = [
        {"status": "Pending", "billNumber": "SJR112"},
        {"status": "Failed", "billNumber": "SR88"},
    ]
    assert state_legend_category(bills) == "failedAdditional"


def test_build_states_payload_includes_doj_and_executive():
    from airtable_fields import LIVE_REVIEW_STATUS_FIELD, REVIEW_STATUS_LIVE

    records = [
        {
            "id": "recOR1",
            "fields": {
                "Name": "USAO plan",
                "State": "OR",
                "Status": "Pending",
                "Bill Number": "",
                LIVE_REVIEW_STATUS_FIELD: REVIEW_STATUS_LIVE,
            },
        },
        {
            "id": "recOR2",
            "fields": {
                "Name": "USAO report",
                "State": "OR",
                "Status": "Passed",
                "Bill Number": "S.982*",
                LIVE_REVIEW_STATUS_FIELD: REVIEW_STATUS_LIVE,
            },
        },
        {
            "id": "recAK1",
            "fields": {
                "Name": "EO",
                "State": "AK",
                "Status": "Passed",
                "Bill Number": "EO13898",
                "Chamber": "Executive",
                LIVE_REVIEW_STATUS_FIELD: REVIEW_STATUS_LIVE,
            },
        },
    ]
    summary, states = build_states_payload(records)
    assert summary["passed"] == 2
    assert summary["pending"] == 1
    assert states["OR"]["category"] == "passedAdditional"
    assert states["AK"]["category"] == "passed"
