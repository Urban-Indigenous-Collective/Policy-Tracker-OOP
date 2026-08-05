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
from indigenous_database import IndigenousDatabase
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
        logger.info("Initializing MainApplication...")
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
        raise


def run_status_refresh_job():
    from discovery.status_refresh import build_pipeline

    logger.info("Starting scheduled status refresh run")
    slack = SlackNotifier()
    try:
        pipeline = build_pipeline(dry_run=False)
        stats = pipeline.run()
        logger.info(
            "Status refresh finished: checked=%d updated=%d unchanged=%d "
            "skipped_non_legiscan=%d resolve_failed=%d getbill_failed=%d "
            "identity_mismatch=%d errors=%d",
            stats.checked,
            stats.updated,
            stats.unchanged,
            stats.skipped_non_legiscan,
            stats.resolve_failed,
            stats.getbill_failed,
            stats.identity_mismatch,
            stats.errors,
        )
    except Exception as exc:
        logger.exception("Status refresh job failed: %s", exc)
        slack.notify_error(f"Status refresh failed: {exc}")
        raise


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
        raise


def run_approval_sync_job():
    logger.info("Starting scheduled approval sync")
    try:
        sync = ApprovalSync()
        stats = sync.run()
        logger.info("Approval sync finished: %s", stats)
    except Exception as exc:
        logger.exception("Approval sync job failed: %s", exc)
        SlackNotifier().notify_error(f"Approval sync failed: {exc}")


def run_indigenous_roster_refresh_job():
    logger.info("Starting scheduled indigenous roster refresh")
    slack = SlackNotifier()
    try:
        db = IndigenousDatabase()
        db.ensure_loaded()
        stats = db.refresh()
        from scripts.enrich_indigenous_ethnicity import run_post_refresh_enrichment

        enrich_stats = run_post_refresh_enrichment(db_path=db.db_path)
        if enrich_stats.get("skipped"):
            logger.info(
                "Post-refresh ethnicity enrichment skipped (%s)",
                enrich_stats.get("reason"),
            )
        else:
            logger.info(
                "Post-refresh ethnicity enrichment: targets=%s accepted=%s applied=%s",
                enrich_stats.get("targets"),
                enrich_stats.get("accepted"),
                enrich_stats.get("applied"),
            )
        app = get_main_app()
        if app.indigenous_db.reload_if_stale():
            logger.info("Reloaded in-memory indigenous roster after refresh")
        logger.info(
            "Indigenous roster refresh finished: count=%d built_at=%s backup=%s",
            stats["count"],
            stats["built_at"],
            stats.get("backup_path"),
        )
    except Exception as exc:
        logger.exception("Indigenous roster refresh failed: %s", exc)
        slack.notify_error(f"Indigenous roster refresh failed: {exc}")


def run_nightly_pipeline():
    """Run discovery, status refresh, and validation refresh sequentially.

    Failure policy:
    - Discovery hard-failure aborts the pipeline (no later steps run).
    - Status refresh or validation refresh failures are logged and notified,
      but the pipeline continues with the next enabled step.
    """
    logger.info("Starting nightly pipeline")
    step = 0
    total_steps = 3

    if _env_flag("DISCOVERY_ENABLED", "true"):
        step += 1
        logger.info("Nightly pipeline step %d/%d: discovery — starting", step, total_steps)
        try:
            run_discovery_job()
        except Exception:
            logger.error("Nightly pipeline aborted after discovery failure")
            return
        logger.info("Nightly pipeline step %d/%d: discovery — complete", step, total_steps)
    else:
        logger.info("Nightly pipeline step 1/%d: discovery — skipped (DISCOVERY_ENABLED=false)", total_steps)

    if _env_flag("STATUS_REFRESH_ENABLED", "true"):
        step += 1
        logger.info("Nightly pipeline step %d/%d: status refresh — starting", step, total_steps)
        try:
            run_status_refresh_job()
        except Exception:
            logger.warning(
                "Nightly pipeline: status refresh failed; continuing to next step"
            )
        else:
            logger.info(
                "Nightly pipeline step %d/%d: status refresh — complete",
                step,
                total_steps,
            )
    else:
        logger.info(
            "Nightly pipeline: status refresh — skipped (STATUS_REFRESH_ENABLED=false)"
        )

    if _env_flag("VALIDATION_REFRESH_ENABLED", "false"):
        step += 1
        logger.info(
            "Nightly pipeline step %d/%d: validation refresh — starting",
            step,
            total_steps,
        )
        try:
            run_validation_refresh_job()
        except Exception:
            logger.warning("Nightly pipeline: validation refresh failed")
        else:
            logger.info(
                "Nightly pipeline step %d/%d: validation refresh — complete",
                step,
                total_steps,
            )
    else:
        logger.info(
            "Nightly pipeline: validation refresh — skipped "
            "(set VALIDATION_REFRESH_ENABLED=true to enable)"
        )

    logger.info("Nightly pipeline finished")


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

    pipeline_cron = os.getenv("NIGHTLY_PIPELINE_CRON") or os.getenv(
        "DISCOVERY_CRON", "0 2 * * *"
    )
    tz = os.getenv("DISCOVERY_TZ", "America/New_York")
    sync_interval = int(os.getenv("APPROVAL_SYNC_INTERVAL_MIN", "10"))

    discovery_enabled = _env_flag("DISCOVERY_ENABLED", "true")
    status_refresh_enabled = _env_flag("STATUS_REFRESH_ENABLED", "true")
    validation_refresh_enabled = _env_flag("VALIDATION_REFRESH_ENABLED", "false")

    scheduler = BlockingScheduler(timezone=tz)

    _add_cron_job(scheduler, "nightly_pipeline", run_nightly_pipeline, pipeline_cron, tz)

    scheduler.add_job(
        run_approval_sync_job,
        IntervalTrigger(minutes=sync_interval),
        id="approval_sync",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    if _env_flag("INDIGENOUS_DB_REFRESH_ENABLED", "false"):
        indigenous_cron = os.getenv("INDIGENOUS_DB_REFRESH_CRON", "0 1 * * 0")
        _add_cron_job(
            scheduler,
            "indigenous_roster_refresh",
            run_indigenous_roster_refresh_job,
            indigenous_cron,
            tz,
        )

    def shutdown(signum, frame):
        logger.info("Shutdown signal received, stopping scheduler")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info(
        "Scheduler started: nightly_pipeline cron=%s tz=%s approval_sync=%dm "
        "steps: discovery=%s status_refresh=%s validation_refresh=%s "
        "indigenous_roster_refresh=%s",
        pipeline_cron,
        tz,
        sync_interval,
        "enabled" if discovery_enabled else "disabled",
        "enabled" if status_refresh_enabled else "disabled",
        "enabled" if validation_refresh_enabled else "disabled",
        "enabled" if _env_flag("INDIGENOUS_DB_REFRESH_ENABLED", "false") else "disabled",
    )
    scheduler.start()


if __name__ == "__main__":
    main()
