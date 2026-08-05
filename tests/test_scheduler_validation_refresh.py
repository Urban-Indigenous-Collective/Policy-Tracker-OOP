"""Scheduler wiring for nightly validation refresh."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

import scheduler


def test_env_flag_defaults_false():
    with patch.dict("os.environ", {}, clear=True):
        assert not scheduler._env_flag("VALIDATION_REFRESH_ENABLED", "false")


def test_env_flag_accepts_true_values():
    with patch.dict("os.environ", {"VALIDATION_REFRESH_ENABLED": "true"}, clear=True):
        assert scheduler._env_flag("VALIDATION_REFRESH_ENABLED", "false")


@pytest.mark.parametrize(
    "cron_expr",
    [
        "0 4 * * *",
        "30 3 * * *",
    ],
)
def test_add_cron_job_registers_job(cron_expr):
    mock_scheduler = MagicMock()
    scheduler._add_cron_job(
        mock_scheduler,
        "validation_refresh",
        scheduler.run_validation_refresh_job,
        cron_expr,
        "America/New_York",
    )
    mock_scheduler.add_job.assert_called_once()
    assert mock_scheduler.add_job.call_args.kwargs["id"] == "validation_refresh"


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


def test_main_skips_validation_refresh_when_disabled():
    with patch.dict(
        "os.environ",
        {
            "LEGISCAN_KEY": "test-key",
            "VALIDATION_REFRESH_ENABLED": "false",
        },
        clear=False,
    ):
        with patch.object(scheduler.BlockingScheduler, "start"):
            with patch.object(scheduler, "_add_cron_job") as mock_add_cron:
                with patch.object(scheduler.BlockingScheduler, "add_job"):
                    scheduler.main()
    job_ids = [call.args[1] for call in mock_add_cron.call_args_list]
    assert job_ids == ["discovery"]
    assert "validation_refresh" not in job_ids


def test_main_registers_validation_refresh_when_enabled():
    with patch.dict(
        "os.environ",
        {
            "LEGISCAN_KEY": "test-key",
            "VALIDATION_REFRESH_ENABLED": "true",
            "VALIDATION_REFRESH_CRON": "0 4 * * *",
        },
        clear=False,
    ):
        with patch.object(scheduler.BlockingScheduler, "start"):
            with patch.object(scheduler, "_add_cron_job") as mock_add_cron:
                with patch.object(scheduler.BlockingScheduler, "add_job"):
                    scheduler.main()
    job_ids = [call.args[1] for call in mock_add_cron.call_args_list]
    assert job_ids == ["discovery", "validation_refresh"]
