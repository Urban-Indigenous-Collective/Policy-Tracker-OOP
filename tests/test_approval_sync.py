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
    assert live["fields"]["Name"] == "MMIP Task Force Act"
    assert "Title" not in live["fields"]
    assert live["fields"]["Bill Overview (Link)"] == "https://example.com/bill/1"
    assert "Bill Overview" not in live["fields"]


def test_approval_sync_maps_somewhat_off_live_select(sync):
    approval_sync, client = sync
    client.pending_table.create(
        {
            "Name": "Inclusive Language Bill",
            "State": "AZ",
            "Bill Overview (Link)": "https://example.com/bill/somewhat",
            "Review Status": "Approved",
            "Gender Inclusive Language?": "Somewhat",
            "Level of Survivor / Relative Input?": "Somewhat",
        }
    )
    stats = approval_sync.run()
    assert stats["approved"] == 1
    assert stats["errors"] == 0
    live = list(client.live_table.records.values())[0]["fields"]
    assert live["Gender Inclusive Language?"] == "TBD or TCRP Specific"
    assert live["Level of Survivor / Relative Input?"] == "Somewhat"


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
    assert pending["fields"]["Bill Overview (Link)"] == "https://example.com/bill/2"
    assert "Bill Overview" not in pending["fields"]


def test_approval_sync_rate_limit_skips_without_slack(sync):
    from unittest.mock import MagicMock

    approval_sync, client = sync
    client.list_pending_approved = MagicMock(
        side_effect=RuntimeError(
            "HTTPSConnectionPool(host='api.airtable.com', port=443): "
            "Max retries exceeded with url: /v0/app/Pending?filterByFormula=... "
            "(Caused by ResponseError('too many 429 error responses'))"
        )
    )
    stats = approval_sync.run()
    assert stats["rate_limited"] == 1
    assert stats["approved"] == 0
    approval_sync.slack.notify_error.assert_not_called()


def test_approval_sync_rate_limit_mid_move_stops(sync):
    from unittest.mock import MagicMock

    approval_sync, client = sync
    client.pending_table.create(
        {
            "Title": "MMIP Task Force Act",
            "State": "NM",
            "Bill Overview": "https://example.com/bill/3",
            "Review Status": "Approved",
        }
    )
    approval_sync.airtable.create_live_record = MagicMock(
        side_effect=RuntimeError("too many 429 error responses")
    )
    stats = approval_sync.run()
    assert stats["rate_limited"] == 1
    approval_sync.slack.notify_error.assert_not_called()


@pytest.mark.parametrize("verify_env,expected_lookups", [("true", 4), ("false", 2)])
def test_approval_sync_verify_flag_controls_post_create_lookups(
    tmp_path, monkeypatch, verify_env, expected_lookups
):
    from discovery.seen_store import SeenStore

    monkeypatch.setenv("APPROVAL_SYNC_VERIFY_WRITES", verify_env)
    client = FakeAirtableClient()
    lookups = []
    original_find = client.find_by_url

    def counting_find(table, url, field="Bill Overview"):
        lookups.append(field)
        # Pre-create checks miss; post-create verify must also miss the link field to force both calls.
        if field == "Bill Overview" and table is client.live_table:
            return original_find(table, url, field)
        return None

    client.find_by_url = counting_find
    client.pending_table.create(
        {
            "Title": "MMIP Task Force Act",
            "State": "NM",
            "Bill Overview": "https://example.com/bill/9",
            "Review Status": "Approved",
        }
    )
    approval_sync = ApprovalSync(
        airtable=client, seen_store=SeenStore(tmp_path / "sync.db"), slack=MagicMock()
    )

    stats = approval_sync.run()

    assert stats["approved"] == 1
    assert len(client.live_table.records) == 1
    assert len(lookups) == expected_lookups
