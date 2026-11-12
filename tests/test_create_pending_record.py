"""create_pending_record must write Main v3 field names (Name), not legacy Title."""

from unittest.mock import MagicMock

from airtable_client import AirtableClient


def test_create_pending_record_maps_legacy_title_to_name(monkeypatch):
    monkeypatch.setenv("AIRTABLE_API_KEY", "test-key")
    monkeypatch.setenv("AIRTABLE_BASE_ID", "appTest")
    monkeypatch.setenv("AIRTABLE_TABLE", "Main v3")
    monkeypatch.setenv("AIRTABLE_PENDING_TABLE", "Pending")

    client = AirtableClient.__new__(AirtableClient)
    client.pending_table = MagicMock()
    created = {}

    def fake_create(fields):
        created["fields"] = fields
        return {"id": "recTEST", "fields": fields}

    client.create_record = lambda table, fields: fake_create(fields)

    client.create_pending_record(
        bill_data={
            "State": "NM",
            "Title": "MMIP Resources",
            "Bill Overview": "https://example.com/mmip",
            "Sponsors": "Agency",
            "Gender Inclusive Explanation": "n/a",
            "Status": "Active",
            "Summary": "Resource page",
            "Validation Warnings": "warn",
        },
        source="State Site",
        relevance_confidence=0.9,
        relevance_rationale="MMIP resources",
        discovered_on="2026-11-12",
    )

    fields = created["fields"]
    assert fields["Name"] == "MMIP Resources"
    assert fields["Bill Overview (Link)"] == "https://example.com/mmip"
    assert fields["Sponsors of the Legislation"] == "Agency"
    assert fields["Gender Inclusive Language"] == "n/a"
    assert fields["Review Status"] == "Pending Review"
    assert fields["Validation Warnings"] == "warn"
    assert "Title" not in fields
    assert "Bill Overview" not in fields
    assert "Categories" not in fields  # empty list omitted (Airtable 422)


def test_create_pending_record_keeps_canonical_name(monkeypatch):
    monkeypatch.setenv("AIRTABLE_API_KEY", "test-key")
    monkeypatch.setenv("AIRTABLE_BASE_ID", "appTest")

    client = AirtableClient.__new__(AirtableClient)
    client.pending_table = MagicMock()
    created = {}
    client.create_record = lambda table, fields: created.setdefault("fields", fields) or {
        "id": "rec2",
        "fields": fields,
    }

    client.create_pending_record(
        bill_data={
            "State": "WA",
            "Name": "Task Force",
            "Bill Overview (Link)": "https://example.com/wa",
            "Status": "Pending",
        },
        source="State Site",
        relevance_confidence=0.8,
        relevance_rationale="task force",
        discovered_on="2026-11-12",
    )

    fields = created["fields"]
    assert fields["Name"] == "Task Force"
    assert fields["Bill Overview (Link)"] == "https://example.com/wa"
    assert "Title" not in fields
