"""Scheduler wiring for the sequential nightly pipeline."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, call, patch

import pytest

import scheduler


@pytest.fixture
def pipeline_env():
    with patch.dict(
        "os.environ",
        {
            "LEGISCAN_KEY": "test-key",
            "DISCOVERY_ENABLED": "true",
            "STATUS_REFRESH_ENABLED": "true",
            "VALIDATION_REFRESH_ENABLED": "true",
        },
        clear=False,
    ):
        yield


def test_run_nightly_pipeline_runs_steps_in_order(pipeline_env):
    call_order: list[str] = []

    def _discovery():
        call_order.append("discovery")

    def _status_refresh():
        call_order.append("status_refresh")

    def _validation_refresh():
        call_order.append("validation_refresh")

    with patch.object(scheduler, "run_discovery_job", side_effect=_discovery):
        with patch.object(scheduler, "run_status_refresh_job", side_effect=_status_refresh):
            with patch.object(
                scheduler, "run_validation_refresh_job", side_effect=_validation_refresh
            ):
                scheduler.run_nightly_pipeline()

    assert call_order == ["discovery", "status_refresh", "validation_refresh"]


def test_run_nightly_pipeline_skips_disabled_steps():
    call_order: list[str] = []

    with patch.dict(
        "os.environ",
        {
            "DISCOVERY_ENABLED": "false",
            "STATUS_REFRESH_ENABLED": "false",
            "VALIDATION_REFRESH_ENABLED": "false",
        },
        clear=False,
    ):
        with patch.object(
            scheduler,
            "run_discovery_job",
            side_effect=lambda: call_order.append("discovery"),
        ):
            with patch.object(
                scheduler,
                "run_status_refresh_job",
                side_effect=lambda: call_order.append("status_refresh"),
            ):
                with patch.object(
                    scheduler,
                    "run_validation_refresh_job",
                    side_effect=lambda: call_order.append("validation_refresh"),
                ):
                    scheduler.run_nightly_pipeline()

    assert call_order == []


def test_run_nightly_pipeline_aborts_after_discovery_failure(pipeline_env):
    with patch.object(scheduler, "run_discovery_job", side_effect=RuntimeError("boom")):
        with patch.object(scheduler, "run_status_refresh_job") as mock_status:
            with patch.object(scheduler, "run_validation_refresh_job") as mock_validation:
                scheduler.run_nightly_pipeline()

    mock_status.assert_not_called()
    mock_validation.assert_not_called()


def test_run_nightly_pipeline_continues_after_status_refresh_failure(pipeline_env):
    with patch.object(scheduler, "run_discovery_job"):
        with patch.object(
            scheduler, "run_status_refresh_job", side_effect=RuntimeError("status fail")
        ):
            with patch.object(scheduler, "run_validation_refresh_job") as mock_validation:
                scheduler.run_nightly_pipeline()

    mock_validation.assert_called_once()


def test_main_registers_single_nightly_pipeline_cron():
    with patch.dict(
        "os.environ",
        {
            "LEGISCAN_KEY": "test-key",
            "NIGHTLY_PIPELINE_CRON": "0 2 * * *",
            "SLACK_DEFER_DISCOVERY": "true",
            "SLACK_SUMMARY_CRON": "30 7 * * *",
            "VALIDATION_REFRESH_ENABLED": "true",
        },
        clear=False,
    ):
        with patch.object(scheduler.BlockingScheduler, "start"):
            with patch.object(scheduler, "_add_cron_job") as mock_add_cron:
                with patch.object(scheduler.BlockingScheduler, "add_job") as mock_add_interval:
                    scheduler.main()

    cron_job_ids = [call.args[1] for call in mock_add_cron.call_args_list]
    assert cron_job_ids == ["nightly_pipeline", "slack_summary"]
    assert "discovery" not in cron_job_ids
    assert "validation_refresh" not in cron_job_ids
    assert "status_refresh" not in cron_job_ids

    interval_job_ids = [call.kwargs["id"] for call in mock_add_interval.call_args_list]
    assert interval_job_ids == ["approval_sync"]


def test_main_falls_back_to_discovery_cron():
    with patch.dict(
        "os.environ",
        {
            "LEGISCAN_KEY": "test-key",
            "DISCOVERY_CRON": "15 1 * * *",
            "SLACK_DEFER_DISCOVERY": "false",
        },
        clear=False,
    ):
        with patch.object(scheduler.BlockingScheduler, "start"):
            with patch.object(scheduler, "_add_cron_job") as mock_add_cron:
                with patch.object(scheduler.BlockingScheduler, "add_job"):
                    scheduler.main()

    pipeline_call = mock_add_cron.call_args_list[0]
    assert pipeline_call.args[1] == "nightly_pipeline"
    assert pipeline_call.args[3] == "15 1 * * *"
    cron_job_ids = [call.args[1] for call in mock_add_cron.call_args_list]
    assert "slack_summary" not in cron_job_ids


def test_run_status_refresh_job_delegates_to_build_pipeline():
    mock_stats = MagicMock(
        checked=5,
        updated=1,
        unchanged=4,
        skipped_non_legiscan=0,
        resolve_failed=0,
        getbill_failed=0,
        identity_mismatch=0,
        errors=0,
    )
    mock_pipeline = MagicMock(run=MagicMock(return_value=mock_stats))
    mock_build = MagicMock(return_value=mock_pipeline)

    with patch("discovery.status_refresh.build_pipeline", mock_build):
        scheduler.run_status_refresh_job()

    mock_build.assert_called_once_with(dry_run=False)
    mock_pipeline.run.assert_called_once()


def test_run_validation_refresh_job_delegates_to_script():
    mock_stats = MagicMock(processed=3, cleared=1, reduced=1, unchanged=1, failed=0)
    mock_run = MagicMock(return_value=mock_stats)
    fake_module = MagicMock(run_validation_refresh=mock_run)
    with patch.dict(
        "os.environ",
        {"VALIDATION_REFRESH_APPLY_EVAL_EXPL_FIXES": "false"},
        clear=False,
    ):
        with patch.dict(
            "sys.modules",
            {"scripts.refresh_pending_validation_warnings": fake_module},
        ):
            scheduler.run_validation_refresh_job()
    mock_run.assert_called_once_with(apply=True, apply_eval_expl_fixes=False)
