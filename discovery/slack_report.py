"""Persist discovery run results for deferred morning Slack delivery."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from discovery.models import utc_now_iso
from slack_client import SlackNotifier

logger = logging.getLogger(__name__)


def report_path() -> Path:
    db_path = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
    return db_path.parent / "pending_slack_report.json"


def should_defer_slack() -> bool:
    if os.getenv("SLACK_BACKFILL_SUMMARY", "false").lower() in ("1", "true", "yes"):
        return False
    return os.getenv("SLACK_DEFER_DISCOVERY", "true").lower() in ("1", "true", "yes")


def discovery_slack_always() -> bool:
    """When true, post a Slack summary even when the run found nothing."""
    return os.getenv("DISCOVERY_SLACK_ALWAYS", "true").lower() in ("1", "true", "yes")


def save_deferred_report(stats, run_at: str | None = None) -> None:
    path = report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_deferred_report() or {}
    payload = {
        "run_at": run_at or stats.run_started_at or utc_now_iso(),
        "run_started_at": stats.run_started_at or existing.get("run_started_at") or "",
        "run_finished_at": stats.run_finished_at or existing.get("run_finished_at") or "",
        "discovered": stats.discovered,
        "analyzed": stats.analyzed,
        "rejected": stats.rejected,
        "skipped": stats.skipped,
        "errors": stats.errors,
        "slack_items": stats.slack_items,
        "by_state": stats.by_state,
        "sources_attempted": stats.sources_attempted or existing.get("sources_attempted") or {},
        "status_items": existing.get("status_items") or [],
        "identity_mismatch_items": existing.get("identity_mismatch_items") or [],
        "status_refresh": existing.get("status_refresh") or {},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Deferred Slack report saved to %s", path)


def merge_status_refresh_report(
    status_items: list[dict[str, Any]],
    refresh_stats: dict[str, Any],
    run_at: str | None = None,
    identity_mismatch_items: list[dict[str, Any]] | None = None,
) -> None:
    """Append status refresh results to the overnight deferred Slack report."""
    path = report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    report = load_deferred_report() or {}
    merged_items = (report.get("status_items") or []) + status_items
    report["status_items"] = merged_items
    if identity_mismatch_items:
        report["identity_mismatch_items"] = (
            report.get("identity_mismatch_items") or []
        ) + identity_mismatch_items
    report["status_refresh"] = refresh_stats
    report.setdefault("run_at", run_at or utc_now_iso())
    report.setdefault("discovered", 0)
    report.setdefault("analyzed", 0)
    report.setdefault("rejected", 0)
    report.setdefault("skipped", 0)
    report.setdefault("errors", 0)
    report.setdefault("slack_items", [])
    report.setdefault("by_state", {})
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(
        "Merged %d status refresh item(s) and %d identity mismatch item(s) "
        "into deferred Slack report at %s",
        len(status_items),
        len(identity_mismatch_items or []),
        path,
    )


def load_deferred_report() -> dict[str, Any] | None:
    path = report_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read deferred Slack report: %s", exc)
        return None


def clear_deferred_report() -> None:
    path = report_path()
    if path.exists():
        path.unlink()


def archive_deferred_report(report: dict[str, Any]) -> Path | None:
    """Copy the deferred Slack report to data/backups/ before clearing."""
    path = report_path()
    if not path.exists():
        return None
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    run_at = str(report.get("run_at") or utc_now_iso())
    stamp = run_at.replace(":", "").replace("+00:00", "Z").replace("-", "")[:15]
    if not stamp:
        from datetime import datetime, timezone

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = backup_dir / f"pending_slack_report-{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Archived deferred Slack report to %s", out)
    return out


def send_deferred_report(slack: SlackNotifier | None = None) -> bool:
    """Post the overnight discovery digest and clear the pending report."""
    report = load_deferred_report()
    if not report:
        logger.info("No deferred discovery report to send")
        return False

    notifier = slack or SlackNotifier(backfill_summary=True)
    status_items = report.get("status_items") or []
    identity_items = report.get("identity_mismatch_items") or []
    slack_items = report.get("slack_items") or []
    has_discovery = bool(slack_items) or any(
        int(report.get(key, 0)) > 0
        for key in ("discovered", "analyzed", "rejected", "skipped", "errors")
    )
    send_empty = discovery_slack_always() and not status_items and not identity_items and not slack_items
    status_refresh = report.get("status_refresh") or {}
    has_status_refresh = bool(status_refresh)
    if (
        not status_items
        and not identity_items
        and not slack_items
        and not has_discovery
        and not has_status_refresh
        and not send_empty
    ):
        logger.info("Deferred report has nothing to send")
        clear_deferred_report()
        return False

    ok = True
    if status_items:
        ok = notifier.notify_status_changes(status_items) and ok
    if identity_items:
        ok = notifier.notify_identity_mismatches(identity_items) and ok
    if slack_items:
        ok = notifier.notify_discovery_batch(slack_items) and ok
    if has_status_refresh or discovery_slack_always():
        ok = notifier.notify_status_refresh_complete(
            checked=int(status_refresh.get("checked", 0)),
            updated=int(status_refresh.get("updated", 0)),
            unchanged=int(status_refresh.get("unchanged", 0)),
            skipped_non_legiscan=int(status_refresh.get("skipped_non_legiscan", 0)),
            resolve_failed=int(status_refresh.get("resolve_failed", 0)),
            getbill_failed=int(status_refresh.get("getbill_failed", 0)),
            identity_mismatch=int(status_refresh.get("identity_mismatch", 0)),
            errors=int(status_refresh.get("errors", 0)),
            always_notify=discovery_slack_always(),
        ) and ok
    if has_discovery or send_empty or discovery_slack_always():
        ok = notifier.notify_run_complete(
            discovered=int(report.get("discovered", 0)),
            analyzed=int(report.get("analyzed", 0)),
            rejected=int(report.get("rejected", 0)),
            skipped=int(report.get("skipped", 0)),
            errors=int(report.get("errors", 0)),
            by_state=report.get("by_state") or {},
            run_started_at=report.get("run_started_at") or report.get("run_at") or "",
            run_finished_at=report.get("run_finished_at") or "",
            sources_attempted=report.get("sources_attempted") or {},
            always_notify=send_empty or discovery_slack_always(),
        ) and ok

    if ok:
        archive_deferred_report(report)
        clear_deferred_report()
        logger.info("Deferred discovery Slack report sent (run_at=%s)", report.get("run_at"))
    return ok
