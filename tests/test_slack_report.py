import json
from unittest.mock import MagicMock, patch

from discovery.slack_report import (
    clear_deferred_report,
    discovery_slack_always,
    load_deferred_report,
    merge_status_refresh_report,
    report_path,
    save_deferred_report,
    send_deferred_report,
    should_defer_slack,
)
from discovery.pipeline import DiscoveryRunStats


def test_should_defer_slack_default():
    with patch.dict("os.environ", {}, clear=True):
        assert should_defer_slack() is True


def test_should_not_defer_during_backfill():
    with patch.dict(
        "os.environ",
        {"SLACK_BACKFILL_SUMMARY": "true", "SLACK_DEFER_DISCOVERY": "true"},
        clear=True,
    ):
        assert should_defer_slack() is False


def test_save_and_send_deferred_report(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    stats = DiscoveryRunStats(
        discovered=3,
        analyzed=1,
        rejected=1,
        skipped=1,
        errors=0,
        slack_items=[
            {
                "state": "VT",
                "title": "Test Bill",
                "summary": "Summary",
                "categories": "MMIP",
                "confidence": 0.9,
                "source_url": "https://example.com/bill",
            }
        ],
        by_state={"VT": {"discovered": 3, "added": 1, "rejected": 1, "skipped": 1, "errors": 0}},
    )
    save_deferred_report(stats, run_at="2026-08-02T02:00:00-04:00")

    loaded = load_deferred_report()
    assert loaded is not None
    assert loaded["analyzed"] == 1
    assert loaded["slack_items"][0]["title"] == "Test Bill"

    slack = MagicMock()
    slack.notify_discovery_batch.return_value = True
    slack.notify_run_complete.return_value = True
    assert send_deferred_report(slack) is True
    slack.notify_status_changes.assert_not_called()
    slack.notify_discovery_batch.assert_called_once()
    slack.notify_run_complete.assert_called_once()
    assert load_deferred_report() is None


def test_merge_status_refresh_report_with_identity_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    stats = DiscoveryRunStats(analyzed=1, slack_items=[{"state": "VT", "title": "New Bill"}])
    save_deferred_report(stats, run_at="2026-08-02T02:00:00-04:00")

    merge_status_refresh_report(
        [],
        {"checked": 1, "updated": 0, "identity_mismatch": 1, "errors": 0},
        run_at="2026-08-02T03:30:00-04:00",
        identity_mismatch_items=[
            {
                "title": "MMIP Reward Fund",
                "state": "MN",
                "table": "Live",
                "airtable_bill_number": "SF36",
                "legiscan_bill_number": "SF3663",
                "source_url": "https://legiscan.com/MN/bill/SF3663/2023",
                "action": "sent_to_pending",
            }
        ],
    )

    loaded = load_deferred_report()
    assert loaded is not None
    assert loaded["status_items"] == []
    assert len(loaded["identity_mismatch_items"]) == 1
    assert loaded["identity_mismatch_items"][0]["title"] == "MMIP Reward Fund"

    slack = MagicMock()
    slack.notify_identity_mismatches.return_value = True
    slack.notify_discovery_batch.return_value = True
    slack.notify_run_complete.return_value = True
    assert send_deferred_report(slack) is True
    slack.notify_status_changes.assert_not_called()
    slack.notify_identity_mismatches.assert_called_once()
    slack.notify_discovery_batch.assert_called_once()
    assert load_deferred_report() is None


def test_merge_status_refresh_report(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    stats = DiscoveryRunStats(analyzed=1, slack_items=[{"state": "VT", "title": "New Bill"}])
    save_deferred_report(stats, run_at="2026-08-02T02:00:00-04:00")

    merge_status_refresh_report(
        [
            {
                "title": "Tracked Bill",
                "state": "NM",
                "table": "Live",
                "source_url": "https://legiscan.com/NM/bill/SB1/2026",
                "changes": [{"field": "Status", "old": "Pending", "new": "Passed"}],
            }
        ],
        {"checked": 1, "updated": 1, "unchanged": 0, "skipped_non_legiscan": 0, "errors": 0},
        run_at="2026-08-02T03:30:00-04:00",
    )

    loaded = load_deferred_report()
    assert loaded is not None
    assert loaded["analyzed"] == 1
    assert len(loaded["status_items"]) == 1
    assert loaded["status_items"][0]["title"] == "Tracked Bill"
    assert loaded["status_refresh"]["updated"] == 1

    slack = MagicMock()
    slack.notify_status_changes.return_value = True
    slack.notify_discovery_batch.return_value = True
    slack.notify_run_complete.return_value = True
    assert send_deferred_report(slack) is True
    slack.notify_status_changes.assert_called_once()
    slack.notify_discovery_batch.assert_called_once()
    assert load_deferred_report() is None


def test_send_deferred_report_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    clear_deferred_report()
    assert send_deferred_report(MagicMock()) is False


def test_discovery_slack_always_default():
    with patch.dict("os.environ", {}, clear=True):
        assert discovery_slack_always() is True


def test_send_deferred_empty_run_when_always_on(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    monkeypatch.setenv("DISCOVERY_SLACK_ALWAYS", "true")
    stats = DiscoveryRunStats(
        run_started_at="2026-08-03T02:00:00-04:00",
        run_finished_at="2026-08-03T02:45:00-04:00",
        sources_attempted={"legiscan": 0, "state_site": 0, "federal_site": 0},
    )
    save_deferred_report(stats, run_at=stats.run_started_at)

    slack = MagicMock()
    slack.notify_run_complete.return_value = True
    assert send_deferred_report(slack) is True
    slack.notify_discovery_batch.assert_not_called()
    slack.notify_run_complete.assert_called_once()
    kwargs = slack.notify_run_complete.call_args.kwargs
    assert kwargs["discovered"] == 0
    assert kwargs["always_notify"] is True
    assert kwargs["run_started_at"] == "2026-08-03T02:00:00-04:00"
    assert load_deferred_report() is None


def test_send_deferred_empty_run_skipped_when_always_off(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    monkeypatch.setenv("DISCOVERY_SLACK_ALWAYS", "false")
    stats = DiscoveryRunStats()
    save_deferred_report(stats, run_at="2026-08-03T02:00:00-04:00")

    slack = MagicMock()
    assert send_deferred_report(slack) is False
    slack.notify_run_complete.assert_not_called()
    assert load_deferred_report() is None
