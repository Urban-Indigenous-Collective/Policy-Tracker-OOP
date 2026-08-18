from unittest.mock import MagicMock, patch

from discovery.status_refresh import StatusRefreshPipeline, diff_status_fields
from legiscan_processor import LegiScanProcessor


class FakeApi:
    def __init__(
        self,
        sessions=None,
        masterlists=None,
        masterlists_raw=None,
        search_results=None,
        text_docs=None,
    ):
        self.sessions = sessions or {}
        self.masterlists = masterlists or {}
        self.masterlists_raw = masterlists_raw or {}
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

    def get_master_list_raw(self, session_id):
        raw = self._lookup(self.masterlists_raw, session_id)
        if raw:
            return {"masterlist": raw}
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

    def log_stats(self):
        pass


def _sample_bill_details(status_code=1, completed=0, year_end=2026):
    return {
        "bill": {
            "bill_id": 12345,
            "bill_number": "SB123",
            "state": "NM",
            "status": status_code,
            "status_date": "2026-03-01",
            "completed": completed,
            "body": "S",
            "change_hash": "abc123",
            "url": "https://legiscan.com/NM/bill/SB123/2026",
            "session": {"year_end": year_end},
            "history": [
                {"date": "2026-02-01", "chamber": "S", "action": "Introduced"},
                {"date": "2026-03-01", "chamber": "S", "action": "Passed Senate"},
            ],
        }
    }


def test_extract_status_fields():
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    fields = proc.extract_status_fields(_sample_bill_details(status_code=2))
    assert fields["Status"] == "Pending"
    assert fields["Progression"] == "Engrossed"
    assert fields["Chamber"] == "Senate"
    assert "Passed Senate" in fields["Chamber Details"]
    assert fields["Last Update"] == "2026-03-01"


def test_extract_status_fields_passed():
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    fields = proc.extract_status_fields(_sample_bill_details(status_code=4, completed=1))
    assert fields["Status"] == "Passed"
    assert fields["Progression"] == "Passed"


def test_diff_status_fields_unchanged():
    current = {
        "Status": "Pending",
        "Progression": "Introduced",
        "Chamber": "Senate",
        "Chamber Details": "2026-02-01 - S: Introduced",
        "Last Update": "2026-02-01",
    }
    fresh = {
        "Status": "Pending",
        "Progression": "Introduced",
        "Chamber": "Senate",
        "Chamber Details": "2026-02-01 - S: Introduced",
        "Last Update": "2026-02-01",
    }
    updates, changes = diff_status_fields(current, fresh)
    assert updates == {}
    assert changes == []


def test_diff_status_fields_detects_progression_change():
    current = {
        "Status": "Pending",
        "Progression": "Introduced",
        "Chamber": "Senate",
        "Chamber Details": "old action",
        "Last Update": "2026-02-01",
    }
    fresh = {
        "Status": "Pending",
        "Progression": "Engrossed",
        "Chamber": "House",
        "Chamber Details": "2026-03-01 - H: Engrossed",
        "Last Update": "2026-03-01",
    }
    updates, changes = diff_status_fields(current, fresh)
    assert updates["Progression"] == "Engrossed"
    assert updates["Chamber"] == "House"
    assert len(changes) == 4
    assert changes[0]["field"] == "Progression"
    assert changes[0]["old"] == "Introduced"
    assert changes[0]["new"] == "Engrossed"


def test_diff_status_fields_blocks_backwards_last_update_only():
    current = {
        "Status": "Pending",
        "Progression": "Introduced",
        "Chamber": "Senate",
        "Chamber Details": "same",
        "Last Update": "2022-03-02",
    }
    fresh = {
        "Status": "Pending",
        "Progression": "Introduced",
        "Chamber": "Senate",
        "Chamber Details": "same",
        "Last Update": "2022-02-03",
    }
    updates, changes = diff_status_fields(current, fresh)
    assert "Last Update" not in updates
    assert changes == []


def test_status_refresh_skips_unchanged_change_hash():
    proc = LegiScanProcessor(
        indigenous_db=None,
        api_client=FakeApi(
            sessions={"NM": [{"session_id": 99, "year_start": 2026, "year_end": 2026}]},
            masterlists_raw={
                99: {
                    "0": {
                        "bill_id": 12345,
                        "number": "SB123",
                        "change_hash": "abc123",
                    }
                }
            },
        ),
    )
    api = MagicMock()
    api.log_stats = MagicMock()

    airtable = MagicMock()
    pending_record = {
        "id": "recPending1",
        "fields": {
            "Name": "MMIP Task Force Act",
            "State": "NM",
            "Bill Overview (Link)": "https://legiscan.com/NM/bill/SB123/2026",
            "Status": "Pending",
            "Progression": "Introduced",
            "Chamber": "Senate",
            "Chamber Details": "2026-02-01 - S: Introduced",
            "Last Update": "2026-02-01",
        },
    }
    airtable.list_pending_for_refresh.return_value = [pending_record]
    airtable.all_live_records.return_value = []

    seen = MagicMock()
    seen.get.return_value = {
        "external_id": "12345",
        "change_hash": "abc123",
        "status": "pending",
    }

    pipeline = StatusRefreshPipeline(
        api_client=api,
        legiscan_processor=proc,
        airtable=airtable,
        seen_store=seen,
        slack=MagicMock(),
        dry_run=True,
    )
    stats = pipeline.run()

    assert stats.checked == 1
    assert stats.skipped_unchanged_hash == 1
    assert stats.getbills_fetched == 0
    api.get_bill_details.assert_not_called()


def test_status_refresh_fetches_bill_when_change_hash_differs():
    proc = LegiScanProcessor(
        indigenous_db=None,
        api_client=FakeApi(
            sessions={"NM": [{"session_id": 99, "year_start": 2026, "year_end": 2026}]},
            masterlists_raw={
                99: {
                    "0": {
                        "bill_id": 12345,
                        "number": "SB123",
                        "change_hash": "new_hash",
                    }
                }
            },
        ),
    )
    api = MagicMock()
    api.get_bill_details.return_value = _sample_bill_details(status_code=2)
    api.log_stats = MagicMock()

    airtable = MagicMock()
    pending_record = {
        "id": "recPending1",
        "fields": {
            "Name": "MMIP Task Force Act",
            "State": "NM",
            "Bill Number": "SB123",
            "Bill Overview (Link)": "https://legiscan.com/NM/bill/SB123/2026",
            "Status": "Pending",
            "Progression": "Introduced",
            "Chamber": "Senate",
            "Chamber Details": "2026-02-01 - S: Introduced",
            "Last Update": "2026-02-01",
        },
    }
    airtable.list_pending_for_refresh.return_value = [pending_record]
    airtable.all_live_records.return_value = []

    seen = MagicMock()
    seen.get.return_value = {
        "external_id": "12345",
        "change_hash": "old_hash",
        "status": "pending",
    }

    pipeline = StatusRefreshPipeline(
        api_client=api,
        legiscan_processor=proc,
        airtable=airtable,
        seen_store=seen,
        slack=MagicMock(),
        dry_run=True,
    )
    stats = pipeline.run()

    assert stats.getbills_fetched == 1
    api.get_bill_details.assert_called_once_with("12345")


def test_status_refresh_pipeline_updates_airtable(monkeypatch):
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    api = MagicMock()
    api.get_bill_details.return_value = _sample_bill_details(status_code=2)

    airtable = MagicMock()
    pending_record = {
        "id": "recPending1",
        "fields": {
            "Name": "MMIP Task Force Act",
            "State": "NM",
            "Review Status": "Pending Review",
            "Bill Overview (Link)": "https://legiscan.com/NM/bill/SB123/2026",
            "Status": "Pending",
            "Progression": "Introduced",
            "Chamber": "Senate",
            "Chamber Details": "2026-02-01 - S: Introduced",
            "Last Update": "2026-02-01",
        },
    }
    airtable.list_pending_for_refresh.return_value = [pending_record]
    airtable.all_live_records.return_value = []
    airtable.pending_table = MagicMock()
    airtable.live_table = MagicMock()

    seen = MagicMock()
    seen.get.return_value = {"external_id": "12345", "status": "pending"}

    pipeline = StatusRefreshPipeline(
        api_client=api,
        legiscan_processor=proc,
        airtable=airtable,
        seen_store=seen,
        slack=MagicMock(),
        dry_run=False,
    )
    monkeypatch.setattr(
        "discovery.status_refresh.should_defer_slack",
        lambda: False,
    )

    with patch("discovery.status_refresh.merge_status_refresh_report") as merge_mock:
        stats = pipeline.run()

    assert stats.checked == 1
    assert stats.updated == 1
    assert stats.status_items[0]["title"] == "MMIP Task Force Act"
    airtable.update_record.assert_called_once()
    update_fields = airtable.update_record.call_args[0][2]
    assert update_fields["Progression"] == "Engrossed"
    assert seen.upsert.called
    merge_mock.assert_not_called()
    pipeline.slack.notify_status_changes.assert_called_once()


def test_status_refresh_resolves_from_bill_text_fallback():
    proc = LegiScanProcessor(indigenous_db=None, api_client=MagicMock())

    def resolve(url, **kw):
        if "MT/bill/HB35/2021" in url:
            return "999"
        return None

    proc.resolve_bill_id = MagicMock(side_effect=resolve)
    api = MagicMock()
    api.get_bill_details.return_value = _sample_bill_details()

    record = {
        "id": "rec1",
        "fields": {
            "Name": "Test",
            "State": "MT",
            "Bill Number": "HB35",
            "Bill Overview (Link)": "https://legiscan.com/MT/bill/HB35/2099",
            "Bill Text": "https://legiscan.com/MT/bill/HB35/2021",
            "Status": "Pending",
            "Progression": "Progression",
            "Chamber": "House",
            "Chamber Details": "old",
            "Last Update": "2021-01-01",
        },
    }
    airtable = MagicMock()
    airtable.list_pending_for_refresh.return_value = [record]
    airtable.all_live_records.return_value = []

    pipeline = StatusRefreshPipeline(
        api_client=api,
        legiscan_processor=proc,
        airtable=airtable,
        seen_store=MagicMock(get=MagicMock(return_value=None), get_by_state_bill=MagicMock(return_value=None)),
        slack=MagicMock(),
        dry_run=True,
    )
    stats = pipeline.run()
    assert stats.checked == 1
    assert proc.resolve_bill_id.call_count >= 1


def test_status_refresh_repairs_text_overview_url():
    proc = LegiScanProcessor(indigenous_db=None, api_client=MagicMock())
    api = MagicMock()
    details = _sample_bill_details(status_code=2)
    api.get_bill_details.return_value = details

    record = {
        "id": "rec1",
        "fields": {
            "Name": "Test",
            "State": "NM",
            "Bill Number": "SB123",
            "Bill Overview (Link)": "https://legiscan.com/NM/text/SB123/id/111/doc.pdf",
            "Status": "Pending",
            "Progression": "Introduced",
            "Chamber": "Senate",
            "Chamber Details": "2026-02-01 - S: Introduced",
            "Last Update": "2026-02-01",
        },
    }
    airtable = MagicMock()
    airtable.list_pending_for_refresh.return_value = [record]
    airtable.all_live_records.return_value = []

    seen = MagicMock()
    seen.get.return_value = {"external_id": "12345"}

    pipeline = StatusRefreshPipeline(
        api_client=api,
        legiscan_processor=proc,
        airtable=airtable,
        seen_store=seen,
        slack=MagicMock(),
        dry_run=False,
    )
    stats = pipeline.run()
    assert stats.updated == 1
    update_fields = airtable.update_record.call_args[0][2]
    assert update_fields["Bill Overview (Link)"] == "https://legiscan.com/NM/bill/SB123/2026"


def test_status_refresh_flags_pending_identity_mismatch():
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    api = MagicMock()
    api.get_bill_details.return_value = _sample_bill_details(status_code=2)

    airtable = MagicMock()
    pending_record = {
        "id": "recPending1",
        "fields": {
            "Name": "Wrong Bill Match",
            "State": "NM",
            "Bill Number": "HB999",
            "Bill Overview (Link)": "https://legiscan.com/NM/bill/SB123/2026",
            "Status": "Pending",
            "Progression": "Introduced",
            "Chamber": "Senate",
            "Chamber Details": "2026-02-01 - S: Introduced",
            "Last Update": "2026-02-01",
        },
    }
    airtable.list_pending_for_refresh.return_value = [pending_record]
    airtable.all_live_records.return_value = []
    airtable.pending_table = MagicMock()

    seen = MagicMock()
    seen.get.return_value = {"external_id": "12345", "status": "pending"}

    pipeline = StatusRefreshPipeline(
        api_client=api,
        legiscan_processor=proc,
        airtable=airtable,
        seen_store=seen,
        slack=MagicMock(),
        dry_run=False,
    )

    stats = pipeline.run()

    assert stats.checked == 1
    assert stats.identity_mismatch == 1
    assert stats.updated == 0
    assert len(stats.identity_mismatch_items) == 1
    assert stats.identity_mismatch_items[0]["airtable_bill_number"] == "HB999"
    assert stats.identity_mismatch_items[0]["legiscan_bill_number"] == "SB123"
    assert stats.identity_mismatch_items[0]["action"] == "flagged"
    airtable.update_record.assert_called_once()
    update_fields = airtable.update_record.call_args[0][2]
    assert "identity mismatch" in update_fields["Validation Warnings"]
    assert "HB999" in update_fields["Validation Warnings"]
    assert "SB123" in update_fields["Validation Warnings"]


def test_status_refresh_sends_live_identity_mismatch_to_pending():
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    api = MagicMock()
    api.get_bill_details.return_value = {
        "bill": {
            **_sample_bill_details(status_code=2)["bill"],
            "bill_number": "SF3663",
        }
    }

    airtable = MagicMock()
    live_record = {
        "id": "recLive1",
        "fields": {
            "Name": "MMIP Reward Fund",
            "State": "MN",
            "Bill Number": "SF36",
            "Review Status": "Live",
            "Bill Overview (Link)": "https://legiscan.com/MN/bill/SF3663/2023",
            "Status": "Passed",
            "Progression": "Passed",
            "Chamber": "Senate",
            "Chamber Details": "2023-05-01 - S: Passed",
            "Last Update": "2023-05-01",
        },
    }
    airtable.list_pending_for_refresh.return_value = []
    airtable.all_live_records.return_value = [live_record]
    airtable.pending_table = MagicMock()
    airtable.live_table = MagicMock()
    airtable.find_by_url.side_effect = [
        None,  # existing check: Bill Overview (Link)
        {"id": "recPendingNew", "fields": {"Review Status": "Pending Review"}},  # verify
    ]
    airtable.create_record.return_value = {"id": "recPendingNew"}
    airtable.record_to_fields.side_effect = lambda record: dict(record.get("fields") or {})

    seen = MagicMock()
    seen.get.return_value = {"external_id": "54321", "status": "approved"}

    pipeline = StatusRefreshPipeline(
        api_client=api,
        legiscan_processor=proc,
        airtable=airtable,
        seen_store=seen,
        slack=MagicMock(),
        dry_run=False,
    )

    stats = pipeline.run()

    assert stats.checked == 1
    assert stats.identity_mismatch == 1
    assert stats.updated == 0
    assert stats.identity_mismatch_items[0]["action"] == "sent_to_pending"
    assert stats.identity_mismatch_items[0]["airtable_bill_number"] == "SF36"
    assert stats.identity_mismatch_items[0]["legiscan_bill_number"] == "SF3663"
    airtable.update_record.assert_called_once()
    airtable.create_record.assert_called_once()
    created_fields = airtable.create_record.call_args[0][1]
    assert created_fields["Review Status"] == "Pending Review"
    assert created_fields["Bill Overview (Link)"] == "https://legiscan.com/MN/bill/SF3663/2023"
    assert "Bill Overview" not in created_fields
    assert "identity mismatch" in created_fields["Validation Warnings"]
    airtable.delete_record.assert_called_once_with(airtable.live_table, "recLive1")
    seen.update_status.assert_called_with(
        "https://legiscan.com/MN/bill/SF3663/2023",
        "pending",
    )


def test_status_refresh_allows_normalized_bill_number_match():
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    api = MagicMock()
    api.get_bill_details.return_value = _sample_bill_details(status_code=2)

    airtable = MagicMock()
    pending_record = {
        "id": "recPending1",
        "fields": {
            "Name": "MMIP Task Force Act",
            "State": "NM",
            "Bill Number": "SB0123",
            "Bill Overview (Link)": "https://legiscan.com/NM/bill/SB123/2026",
            "Status": "Pending",
            "Progression": "Introduced",
            "Chamber": "Senate",
            "Chamber Details": "2026-02-01 - S: Introduced",
            "Last Update": "2026-02-01",
        },
    }
    airtable.list_pending_for_refresh.return_value = [pending_record]
    airtable.all_live_records.return_value = []
    airtable.pending_table = MagicMock()

    seen = MagicMock()
    seen.get.return_value = {"external_id": "12345", "status": "pending"}

    pipeline = StatusRefreshPipeline(
        api_client=api,
        legiscan_processor=proc,
        airtable=airtable,
        seen_store=seen,
        slack=MagicMock(),
        dry_run=False,
    )

    stats = pipeline.run()

    assert stats.checked == 1
    assert stats.identity_mismatch == 0
    assert stats.updated == 1
    airtable.update_record.assert_called_once()


def test_status_refresh_skips_non_legiscan():
    proc = LegiScanProcessor(indigenous_db=None, api_client=FakeApi())
    airtable = MagicMock()
    airtable.list_pending_for_refresh.return_value = [
        {
            "id": "rec1",
            "fields": {
                "Name": "Gov Bill",
                "Bill Overview (Link)": "https://legislature.example.gov/bill/1",
                "Status": "Pending",
                "Progression": "Introduced",
            },
        }
    ]
    airtable.all_live_records.return_value = []

    pipeline = StatusRefreshPipeline(
        api_client=MagicMock(),
        legiscan_processor=proc,
        airtable=airtable,
        seen_store=MagicMock(),
        slack=MagicMock(),
        dry_run=False,
    )
    stats = pipeline.run()
    assert stats.skipped_non_legiscan == 1
    assert stats.checked == 0
    airtable.update_record.assert_not_called()
