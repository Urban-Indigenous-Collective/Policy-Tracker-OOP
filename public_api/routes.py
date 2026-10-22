"""Flask blueprint for /api/v1 public read endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from public_api.cache import UpstreamUnavailableError, get_snapshot
from public_api.serialize import record_to_bill_dto
from public_api.states import normalize_public_state

public_api_bp = Blueprint("public_api", __name__, url_prefix="/api/v1")


def _error(code: str, message: str, http_status: int):
    return jsonify({"error": code, "message": message}), http_status


@public_api_bp.get("/health")
def health():
    try:
        snap = get_snapshot()
        return jsonify(
            {
                "ok": True,
                "liveCount": snap.live_count,
                "mainV3Count": snap.main_v3_count,
                "cacheAgeSeconds": round(snap.cache_age_seconds, 1),
                "policyDataAsOf": snap.policy_data_as_of.isoformat()
                if snap.policy_data_as_of
                else None,
                "generatedAt": snap.generated_at.isoformat(),
            }
        )
    except UpstreamUnavailableError as exc:
        return _error("upstream_unavailable", str(exc), 503)


@public_api_bp.get("/states")
def list_states():
    try:
        snap = get_snapshot()
    except UpstreamUnavailableError as exc:
        return _error("upstream_unavailable", str(exc), 503)

    return jsonify(
        {
            "summary": snap.summary,
            "states": snap.states,
            "liveCount": snap.live_count,
            "mainV3Count": snap.main_v3_count,
            "policyDataAsOf": snap.policy_data_as_of.isoformat()
            if snap.policy_data_as_of
            else None,
            "generatedAt": snap.generated_at.isoformat(),
            "cacheAgeSeconds": round(snap.cache_age_seconds, 1),
        }
    )


@public_api_bp.get("/states/<code>/bills")
def state_bills(code: str):
    try:
        snap = get_snapshot()
    except UpstreamUnavailableError as exc:
        return _error("upstream_unavailable", str(exc), 503)

    normalized = normalize_public_state(code)
    bills = snap.by_state.get(normalized)
    if bills is None:
        return _error("not_found", f"No public bills for state {code!r}", 404)

    return jsonify(
        {
            "state": normalized,
            "bills": bills,
            "generatedAt": snap.generated_at.isoformat(),
            "cacheAgeSeconds": round(snap.cache_age_seconds, 1),
        }
    )


@public_api_bp.get("/bills/<record_id>")
def bill_detail(record_id: str):
    try:
        snap = get_snapshot()
    except UpstreamUnavailableError as exc:
        return _error("upstream_unavailable", str(exc), 503)

    record = next((r for r in snap.records if r.get("id") == record_id), None)
    if record is None:
        return _error("not_found", f"Bill {record_id!r} not found", 404)

    return jsonify(
        {
            "bill": record_to_bill_dto(record, include_analysis=True),
            "generatedAt": snap.generated_at.isoformat(),
            "cacheAgeSeconds": round(snap.cache_age_seconds, 1),
        }
    )
