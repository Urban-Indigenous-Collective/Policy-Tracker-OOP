"""Tests for LegiScan quota Slack digest helpers."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from discovery.legiscan_quota import (
    ensure_legiscan_quota_in_report,
    format_resume_date,
    legiscan_quota_payload,
    legiscan_quota_reset_date,
    merge_legiscan_quota,
)
from discovery.pipeline import DiscoveryRunStats
from discovery.slack_report import merge_status_refresh_report, save_deferred_report, send_deferred_report


def test_legiscan_quota_reset_date_mid_month():
    assert legiscan_quota_reset_date(datetime(2026, 8, 15, tzinfo=timezone.utc)) == date(2026, 9, 1)


def test_format_resume_date():
    assert format_resume_date(date(2026, 9, 1)) == "September 1, 2026"


def test_merge_legiscan_quota_combines_flags():
    merged = merge_legiscan_quota(
        legiscan_quota_payload(discovery_limited=True),
        legiscan_quota_payload(status_refresh_limited=True),
    )
    assert merged["limited"] is True
    assert merged["discovery_limited"] is True
    assert merged["status_refresh_limited"] is True


def test_infer_quota_from_getbill_failure_pattern():
    report = {
        "discovered": 0,
        "analyzed": 0,
        "sources_attempted": {},
        "status_refresh": {
            "checked": 238,
            "updated": 0,
            "unchanged": 0,
            "skipped_non_legiscan": 120,
            "getbill_failed": 238,
            "getbills_fetched": 238,
        },
    }
    enriched = ensure_legiscan_quota_in_report(report)
    assert enriched["legiscan_quota"]["limited"] is True
    assert enriched["legiscan_quota"]["status_refresh_limited"] is True
    assert "September 1, 2026" in enriched["legiscan_quota"]["resume_date_display"]


def test_send_deferred_suppresses_raw_heartbeats_when_quota_inferred(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    stats = DiscoveryRunStats(
        run_started_at="2026-08-17T06:00:00+00:00",
        run_finished_at="2026-08-17T06:00:01+00:00",
    )
    save_deferred_report(stats, run_at=stats.run_started_at)
    merge_status_refresh_report(
        [],
        {
            "checked": 238,
            "updated": 0,
            "unchanged": 0,
            "skipped_non_legiscan": 120,
            "getbill_failed": 238,
            "getbills_fetched": 238,
        },
    )

    slack = MagicMock()
    slack.notify_legiscan_quota_digest.return_value = True
    assert send_deferred_report(slack) is True
    slack.notify_legiscan_quota_digest.assert_called_once()
    slack.notify_status_refresh_complete.assert_not_called()
    slack.notify_run_complete.assert_not_called()


def test_send_deferred_report_includes_quota_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    stats = DiscoveryRunStats(
        run_started_at="2026-08-15T02:00:00-04:00",
        run_finished_at="2026-08-15T02:30:00-04:00",
        legiscan_limited=True,
        legiscan_limit_reason="monthly query limit exceeded",
        sources_attempted={"legiscan": 0, "state_site": 3, "federal_site": 5},
    )
    save_deferred_report(stats, run_at=stats.run_started_at)
    merge_status_refresh_report(
        [],
        {"checked": 0, "updated": 0, "legiscan_limited": True},
        legiscan_quota=legiscan_quota_payload(status_refresh_limited=True),
    )

    slack = MagicMock()
    slack.notify_legiscan_quota_digest.return_value = True
    slack.notify_run_complete.return_value = True
    assert send_deferred_report(slack) is True
    slack.notify_legiscan_quota_digest.assert_called_once()
    report = slack.notify_legiscan_quota_digest.call_args.args[0]
    assert report["legiscan_quota"]["limited"] is True
    assert "September 1, 2026" in report["legiscan_quota"]["resume_date_display"]
