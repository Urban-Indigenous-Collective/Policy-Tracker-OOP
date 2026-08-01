from unittest.mock import MagicMock

import pytest

from approval_sync import ApprovalSync
from airtable_fields import REVIEW_STATUS_LIVE, REVIEW_STATUS_PENDING


class FakeTable:
    def __init__(self):
        self.records = {}

    def create(self, fields):
        rid = f"rec{len(self.records) + 1}"
        self.records[rid] = {"id": rid, "fields": dict(fields)}
        return self.records[rid]

    def update(self, record_id, fields):
        self.records[record_id]["fields"].update(fields)
        return self.records[record_id]

    def delete(self, record_id):
        del self.records[record_id]

    def all(self, formula=None):
        results = list(self.records.values())
        if formula and "Approved" in formula:
            return [r for r in results if r["fields"].get("Review Status") == "Approved"]
        if formula and "Send Back to Pending" in formula:
            return [
                r
                for r in results
                if r["fields"].get("Review Status") == "Send Back to Pending"
            ]
        if formula and "Rejected" in formula:
            return [r for r in results if r["fields"].get("Review Status") == "Rejected"]
        if formula and "Bill Overview" in formula:
            for r in results:
                url = r["fields"].get("Bill Overview") or r["fields"].get("Bill Overview (Link)")
                if url and url in formula:
                    return [r]
        return []


class FakeAirtableClient:
    def __init__(self):
        self.pending_table = FakeTable()
        self.live_table = FakeTable()

    def list_pending_approved(self):
        return self.pending_table.all(formula="{Review Status} = 'Approved'")

    def list_live_send_back(self):
        return self.live_table.all(formula="{Review Status} = 'Send Back to Pending'")

    def list_pending_rejected(self):
        return self.pending_table.all(formula="{Review Status} = 'Rejected'")

    def find_by_url(self, table, url, field="Bill Overview"):
        for record in table.records.values():
            fields = record["fields"]
            if fields.get(field) == url or fields.get("Bill Overview (Link)") == url:
                return record
        return None

    def create_record(self, table, fields):
        return table.create(fields)

    def create_live_record(self, fields):
        fields = dict(fields)
        fields["Review Status"] = REVIEW_STATUS_LIVE
        return self.live_table.create(fields)

    def delete_record(self, table, record_id):
        table.delete(record_id)

    def record_to_fields(self, record):
        return dict(record["fields"])

    def pending_record_url(self, record):
        fields = record["fields"]
        return fields.get("Bill Overview") or fields.get("Bill Overview (Link)") or ""


@pytest.fixture
def sync(tmp_path):
    from discovery.seen_store import SeenStore

    client = FakeAirtableClient()
    store = SeenStore(tmp_path / "sync.db")
    slack = MagicMock()
    slack.notify_approval = MagicMock(return_value=True)
    return ApprovalSync(airtable=client, seen_store=store, slack=slack), client


def test_approval_sync_pending_to_live(sync):
    approval_sync, client = sync
    pending = client.pending_table.create(
        {
            "Title": "MMIP Task Force Act",
            "State": "NM",
            "Bill Overview": "https://example.com/bill/1",
            "Review Status": "Approved",
        }
    )
    stats = approval_sync.run()
    assert stats["approved"] == 1
    assert len(client.pending_table.records) == 0
    assert len(client.live_table.records) == 1
    live = list(client.live_table.records.values())[0]
    assert live["fields"]["Review Status"] == REVIEW_STATUS_LIVE
    assert live["fields"]["Bill Overview (Link)"] == "https://example.com/bill/1"


def test_approval_sync_live_to_pending(sync):
    approval_sync, client = sync
    client.live_table.create(
        {
            "Title": "MMIP Task Force Act",
            "State": "NM",
            "Bill Overview (Link)": "https://example.com/bill/2",
            "Review Status": "Send Back to Pending",
        }
    )
    stats = approval_sync.run()
    assert stats["send_back"] == 1
    assert len(client.live_table.records) == 0
    assert len(client.pending_table.records) == 1
    pending = list(client.pending_table.records.values())[0]
    assert pending["fields"]["Review Status"] == REVIEW_STATUS_PENDING
