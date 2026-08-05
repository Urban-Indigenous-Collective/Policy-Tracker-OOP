#!/usr/bin/env python3
"""Nightly scheduler for MMIP discovery and approval sync."""

import logging
import os
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from approval_sync import ApprovalSync
from discovery.pipeline import DiscoveryPipeline
from main_application import MainApplication
from slack_client import SlackNotifier

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_main_app: MainApplication | None = None


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


def get_main_app() -> MainApplication:
    global _main_app
    if _main_app is None:
        legiscan_key = os.getenv("LEGISCAN_KEY")
        if not legiscan_key:
            raise ValueError("LEGISCAN_KEY must be set for scheduler")
        logger.info("Initializing MainApplication (Indigenous DB build may take 30-60s)...")
        _main_app = MainApplication(legiscan_key)
    return _main_app


def run_discovery_job():
    logger.info("Starting scheduled discovery run")
    slack = SlackNotifier()
    try:
        app = get_main_app()
        pipeline = DiscoveryPipeline(main_app=app)
        stats = pipeline.run()
        logger.info(
            "Discovery run finished: analyzed=%d rejected=%d skipped=%d errors=%d",
            stats.analyzed,
            stats.rejected,
            stats.skipped,
            stats.errors,
        )
    except Exception as exc:
        logger.exception("Discovery job failed: %s", exc)
        slack.notify_error(str(exc))


def run_approval_sync_job():
    logger.info("Starting scheduled approval sync")
    try:
        sync = ApprovalSync()
        stats = sync.run()
        logger.info("Approval sync finished: %s", stats)
    except Exception as exc:
        logger.exception("Approval sync job failed: %s", exc)
        SlackNotifier().notify_error(f"Approval sync failed: {exc}")


def run_validation_refresh_job():
    from scripts.refresh_pending_validation_warnings import run_validation_refresh

    apply_eval_expl_fixes = _env_flag("VALIDATION_REFRESH_APPLY_EVAL_EXPL_FIXES", "false")
    logger.info(
        "Starting scheduled validation refresh (apply_eval_expl_fixes=%s)",
        apply_eval_expl_fixes,
    )
    slack = SlackNotifier()
    try:
        stats = run_validation_refresh(
            apply=True,
            apply_eval_expl_fixes=apply_eval_expl_fixes,
        )
        logger.info(
            "Validation refresh finished: processed=%d cleared=%d reduced=%d "
            "unchanged=%d failed=%d",
            stats.processed,
            stats.cleared,
            stats.reduced,
            stats.unchanged,
            stats.failed,
        )
    except Exception as exc:
        logger.exception("Validation refresh job failed: %s", exc)
        slack.notify_error(f"Validation refresh failed: {exc}")


def _add_cron_job(scheduler, job_id, func, cron_expr, tz):
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron (expected 5 fields): {cron_expr}")
    minute, hour, day, month, day_of_week = parts
    scheduler.add_job(
        func,
        CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=tz,
        ),
        id=job_id,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )


def main():
    load_dotenv()

    if not os.getenv("DISCOVERY_ENABLED", "true").lower() in ("1", "true", "yes"):
        logger.warning("DISCOVERY_ENABLED is false; scheduler will only run approval sync")

    cron_expr = os.getenv("DISCOVERY_CRON", "0 2 * * *")
    tz = os.getenv("DISCOVERY_TZ", "America/New_York")
    sync_interval = int(os.getenv("APPROVAL_SYNC_INTERVAL_MIN", "10"))
    validation_refresh_enabled = _env_flag("VALIDATION_REFRESH_ENABLED", "false")
    validation_refresh_cron = os.getenv("VALIDATION_REFRESH_CRON", "0 4 * * *")

    scheduler = BlockingScheduler(timezone=tz)

    _add_cron_job(scheduler, "discovery", run_discovery_job, cron_expr, tz)

    scheduler.add_job(
        run_approval_sync_job,
        IntervalTrigger(minutes=sync_interval),
        id="approval_sync",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    if validation_refresh_enabled:
        _add_cron_job(
            scheduler,
            "validation_refresh",
            run_validation_refresh_job,
            validation_refresh_cron,
            tz,
        )
    else:
        logger.info(
            "Validation refresh disabled (set VALIDATION_REFRESH_ENABLED=true to enable)"
        )

    def shutdown(signum, frame):
        logger.info("Shutdown signal received, stopping scheduler")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info(
        "Scheduler started: discovery cron=%s tz=%s approval_sync=%dm validation_refresh=%s%s",
        cron_expr,
        tz,
        sync_interval,
        "enabled" if validation_refresh_enabled else "disabled",
        f" cron={validation_refresh_cron}" if validation_refresh_enabled else "",
    )
    scheduler.start()


if __name__ == "__main__":
    main()
