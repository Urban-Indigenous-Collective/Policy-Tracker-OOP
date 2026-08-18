"""LegiScan monthly quota helpers and non-LegiScan source labels for Slack digests."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from api_client import LegiScanAPIError, LegiScanDisabledError, LegiScanOverlimitError

# Discovery / monitoring paths that do not consume LegiScan API quota.
ACTIVE_NON_LEGISCAN_SOURCES: tuple[str, ...] = (
    "State government websites (executive orders, proclamations, agency pages)",
    "Federal Register (executive orders and presidential documents)",
    "DOJ press releases and U.S. Attorney office listings",
    "Pending ↔ Live approval sync (Airtable)",
    "Indigenous legislator roster refresh (weekly, when enabled)",
)


def legiscan_quota_reset_date(reference: datetime | None = None) -> date:
    """LegiScan public API quota resets at midnight on the 1st of each month."""
    ref = reference or datetime.now(timezone.utc)
    today = ref.date()
    if today.day == 1:
        return today
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


def format_resume_date(resume: date) -> str:
    return f"{resume.strftime('%B')} {resume.day}, {resume.year}"


def is_legiscan_limit_error(exc: BaseException) -> bool:
    if isinstance(exc, (LegiScanOverlimitError, LegiScanDisabledError)):
        return True
    if isinstance(exc, LegiScanAPIError):
        text = str(exc).lower()
        return any(
            marker in text
            for marker in ("overlimit", "query limit", "monthly limit", "quota")
        )
    return False


def legiscan_quota_payload(
    *,
    limited: bool = True,
    reason: str = "",
    resume_date: date | None = None,
    discovery_limited: bool = False,
    status_refresh_limited: bool = False,
) -> dict[str, Any]:
    resume = resume_date or legiscan_quota_reset_date()
    return {
        "limited": limited,
        "reason": reason,
        "resume_date": resume.isoformat(),
        "resume_date_display": format_resume_date(resume),
        "discovery_limited": discovery_limited,
        "status_refresh_limited": status_refresh_limited,
        "active_sources": list(ACTIVE_NON_LEGISCAN_SOURCES),
    }


def merge_legiscan_quota(existing: dict[str, Any] | None, update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing or {})
    discovery_limited = bool(merged.get("discovery_limited")) or bool(update.get("discovery_limited"))
    status_refresh_limited = bool(merged.get("status_refresh_limited")) or bool(
        update.get("status_refresh_limited")
    )
    limited = bool(merged.get("limited")) or bool(update.get("limited"))
    skip_keys = {"limited", "discovery_limited", "status_refresh_limited"}
    merged.update(
        {k: v for k, v in update.items() if v is not None and k not in skip_keys}
    )
    merged["limited"] = limited or discovery_limited or status_refresh_limited
    merged["discovery_limited"] = discovery_limited
    merged["status_refresh_limited"] = status_refresh_limited
    if update.get("reason") and not merged.get("reason"):
        merged["reason"] = update["reason"]
    if not merged.get("resume_date_display"):
        resume_raw = merged.get("resume_date")
        if resume_raw:
            merged["resume_date_display"] = format_resume_date(date.fromisoformat(str(resume_raw)))
    if not merged.get("active_sources"):
        merged["active_sources"] = list(ACTIVE_NON_LEGISCAN_SOURCES)
    return merged


def infer_legiscan_quota_from_report(report: dict[str, Any]) -> dict[str, Any] | None:
    """Detect quota exhaustion from overnight run stats when no exception was recorded."""
    status_refresh = report.get("status_refresh") or {}
    checked = int(status_refresh.get("checked", 0))
    getbill_failed = int(status_refresh.get("getbill_failed", 0))
    getbills_fetched = int(status_refresh.get("getbills_fetched", 0) or getbill_failed)
    updated = int(status_refresh.get("updated", 0))
    unchanged = int(status_refresh.get("unchanged", 0))
    skipped_non_legiscan = int(status_refresh.get("skipped_non_legiscan", 0))
    legiscan_checked = max(checked - skipped_non_legiscan, 0)

    status_refresh_limited = False
    discovery_limited = False
    reason = ""

    if legiscan_checked >= 3 and getbill_failed >= 3 and updated == 0 and unchanged == 0:
        if getbill_failed >= legiscan_checked or getbill_failed >= getbills_fetched:
            status_refresh_limited = True
            reason = (
                f"LegiScan getBill failed for {getbill_failed} of {legiscan_checked} "
                "tracked bills (monthly API limit likely reached)"
            )

    if bool(status_refresh.get("legiscan_limited")):
        status_refresh_limited = True
        reason = reason or str(status_refresh.get("legiscan_limit_reason") or "")

    sources = report.get("sources_attempted") or {}
    discovered = int(report.get("discovered", 0))
    if bool(report.get("legiscan_limited")) or (
        int(sources.get("legiscan", -1)) == 0
        and discovered == 0
        and int(report.get("analyzed", 0)) == 0
        and (status_refresh_limited or getbill_failed > 0)
    ):
        discovery_limited = True
        if not reason:
            reason = str(report.get("legiscan_limit_reason") or "LegiScan search unavailable")

    if not status_refresh_limited and not discovery_limited:
        return None

    return legiscan_quota_payload(
        reason=reason,
        discovery_limited=discovery_limited,
        status_refresh_limited=status_refresh_limited,
    )


def ensure_legiscan_quota_in_report(report: dict[str, Any]) -> dict[str, Any]:
    """Merge explicit or inferred quota state into a deferred Slack report."""
    quota = dict(report.get("legiscan_quota") or {})
    if not quota.get("limited"):
        inferred = infer_legiscan_quota_from_report(report)
        if inferred:
            quota = merge_legiscan_quota(quota, inferred)
    report["legiscan_quota"] = quota
    return report
