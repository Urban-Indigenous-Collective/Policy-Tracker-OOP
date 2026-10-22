"""Map legend categories and hero summary stats from Live bills."""

from __future__ import annotations

from typing import Any, Literal

from public_api.serialize import record_to_bill_dto
from public_api.states import is_map_state_code, normalize_public_state
from slack_client import STATE_NAMES

LegendCategory = Literal[
    "passed",
    "passedAdditional",
    "pending",
    "failed",
    "failedAdditional",
]

_STATUS_PASSED = "passed"
_STATUS_PENDING = "pending"
_STATUS_FAILED = "failed"


def _norm_status(raw: str) -> str:
    return str(raw or "").strip().lower()


def state_legend_category(bills: list[dict[str, Any]]) -> LegendCategory | None:
    """Apply UIC map-key rules to bill DTOs for one state (Main v3 ``Status`` only)."""
    if not bills:
        return None

    statuses = [_norm_status(b.get("status")) for b in bills]
    has_passed = _STATUS_PASSED in statuses
    has_pending = _STATUS_PENDING in statuses
    has_failed = _STATUS_FAILED in statuses

    if has_passed:
        return "passedAdditional" if has_pending else "passed"

    if has_pending:
        non_pending = [s for s in statuses if s != _STATUS_PENDING]
        if non_pending and all(s == _STATUS_FAILED for s in non_pending) and has_failed:
            return "failedAdditional"
        return "pending"

    if has_failed:
        return "failed"

    return "pending"


def build_summary_stats(bills: list[dict[str, Any]]) -> dict[str, int]:
    passed = pending = rejected = 0
    for bill in bills:
        status = _norm_status(bill.get("status"))
        if status == _STATUS_PASSED:
            passed += 1
        elif status == _STATUS_PENDING:
            pending += 1
        elif status == _STATUS_FAILED:
            rejected += 1
    return {"passed": passed, "pending": pending, "rejected": rejected}


def build_states_payload(
    records: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    """Return (summary, states map) from Airtable records."""
    bills = [record_to_bill_dto(record) for record in records]
    summary = build_summary_stats(bills)

    by_state: dict[str, list[dict[str, Any]]] = {}
    for bill in bills:
        code = bill["state"]
        by_state.setdefault(code, []).append(bill)

    states: dict[str, dict[str, Any]] = {}
    for code, state_bills in by_state.items():
        if not is_map_state_code(code):
            continue
        category = state_legend_category(state_bills)
        if category is None:
            continue
        states[code] = {
            "code": code,
            "name": STATE_NAMES.get(code, code),
            "category": category,
            "billCount": len(state_bills),
        }

    return summary, states
