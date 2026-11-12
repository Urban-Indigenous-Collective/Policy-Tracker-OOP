"""Flask routes for /api/v1/subscriptions."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, request

from discovery.federal_schema import FEDERAL_STATE
from public_api.states import is_map_state_code, normalize_public_state
from subscriptions.config import request_code_rate_limit, subscriptions_enabled
from subscriptions.mail import (
    MailDeliveryError,
    send_subscription_code,
    send_subscription_welcome,
)
from subscriptions.store import (
    add_state,
    create_otp,
    get_monthly_digest,
    get_states,
    is_valid_email,
    normalize_email,
    remove_state,
    resolve_session,
    set_monthly_digest,
    verify_magic_link,
    verify_otp,
)

subscriptions_bp = Blueprint(
    "subscriptions", __name__, url_prefix="/api/v1/subscriptions"
)
logger = logging.getLogger(__name__)

# In-process rate limit: key → deque of request timestamps
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def register_subscriptions_api(app) -> None:
    app.register_blueprint(subscriptions_bp)


def _error(code: str, message: str, http_status: int):
    return jsonify({"error": code, "message": message}), http_status


def _feature_off():
    return _error("not_found", "State subscriptions are disabled", 404)


def _normalize_subscribable_state(raw: str | None) -> str | None:
    if raw is None or str(raw).strip() == "":
        return None
    normalized = normalize_public_state(raw)
    if is_map_state_code(normalized) or normalized == FEDERAL_STATE:
        return normalized
    return None


def _session_email_from_request() -> tuple[str | None, object | None]:
    auth = request.headers.get("Authorization") or ""
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        body = request.get_json(silent=True) or {}
        token = str(body.get("sessionToken") or "").strip()
    if not token:
        token = str(request.args.get("sessionToken") or "").strip()
    email = resolve_session(token)
    if not email:
        return None, _error("unauthorized", "Valid session required", 401)
    return email, None


def _rate_limited(key: str) -> bool:
    max_requests, window = request_code_rate_limit()
    now = time.time()
    bucket = _rate_buckets[key]
    while bucket and bucket[0] < now - window:
        bucket.popleft()
    if len(bucket) >= max_requests:
        return True
    bucket.append(now)
    return False


def reset_rate_limits_for_tests() -> None:
    _rate_buckets.clear()


@subscriptions_bp.get("/status")
def status():
    if not subscriptions_enabled():
        return _feature_off()
    return jsonify({"enabled": True})


def _client_ip() -> str:
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if "," in client_ip:
        return client_ip.split(",", 1)[0].strip()
    return client_ip


@subscriptions_bp.post("/signup")
def signup():
    """Always add the requested state immediately (no OTP).

    OTP is only sent when the client later asks to manage via ``/request-code``.
    If the email already had subscriptions, the response flags that so the UI
    can offer an optional manage path.
    """
    if not subscriptions_enabled():
        return _feature_off()
    body = request.get_json(silent=True) or {}
    email = normalize_email(str(body.get("email") or ""))
    state = _normalize_subscribable_state(body.get("state"))
    if not is_valid_email(email):
        return _error("invalid_email", "A valid email address is required", 400)
    if not state:
        return _error("invalid_state", "A valid state code is required", 400)

    rate_key = f"{_client_ip()}|{email}"
    if _rate_limited(rate_key):
        return _error("rate_limited", "Too many requests; try again later", 429)

    prior = get_states(email)
    had_prior = bool(prior)
    already_had_state = state in prior
    states = add_state(email, state)

    if not had_prior:
        try:
            send_subscription_welcome(email, state)
        except MailDeliveryError:
            logger.exception("state_subscribe welcome mail failed for %s", email)
            return _error(
                "mail_failed",
                "Subscribed, but the confirmation email could not be sent",
                502,
            )
        message = f"Subscribed to updates for {state}."
    elif already_had_state:
        message = (
            f"You're already subscribed to updates for {state}. "
            "This email already has subscriptions — "
            "verify to manage or unsubscribe."
        )
    else:
        message = (
            f"Subscribed to updates for {state}. "
            "This email already has other subscriptions — "
            "verify to manage or unsubscribe."
        )

    return jsonify(
        {
            "ok": True,
            "status": "subscribed",
            "email": email,
            "state": state,
            "states": states,
            "added": False if already_had_state else state,
            "alreadySubscribed": already_had_state,
            "hasExistingSubscriptions": had_prior,
            "message": message,
        }
    )


@subscriptions_bp.post("/request-code")
def request_code():
    """Resend OTP for an existing subscriber managing their list."""
    if not subscriptions_enabled():
        return _feature_off()
    body = request.get_json(silent=True) or {}
    email = normalize_email(str(body.get("email") or ""))
    state = _normalize_subscribable_state(body.get("state"))
    if not is_valid_email(email):
        return _error("invalid_email", "A valid email address is required", 400)
    if not state:
        return _error("invalid_state", "A valid state code is required", 400)

    rate_key = f"{_client_ip()}|{email}"
    if _rate_limited(rate_key):
        return _error("rate_limited", "Too many verification requests; try again later", 429)

    existing = get_states(email)
    if not existing:
        return _error(
            "not_subscribed",
            "No existing subscriptions for this email; use signup instead",
            400,
        )

    code, magic = create_otp(email, state)
    try:
        send_subscription_code(email, code, state, magic_token=magic)
    except MailDeliveryError:
        logger.exception("state_subscribe OTP mail failed for %s", email)
        return _error(
            "mail_failed",
            "Could not send the verification email; try again shortly",
            502,
        )
    return jsonify(
        {
            "ok": True,
            "status": "verification_required",
            "email": email,
            "state": state,
            "hasExistingSubscriptions": True,
            "message": (
                "If that address can receive mail, a verification code "
                "and manage link were sent."
            ),
        }
    )


@subscriptions_bp.post("/verify")
def verify():
    if not subscriptions_enabled():
        return _feature_off()
    body = request.get_json(silent=True) or {}
    email = normalize_email(str(body.get("email") or ""))
    code = str(body.get("code") or "").strip()
    if not is_valid_email(email):
        return _error("invalid_email", "A valid email address is required", 400)
    if not (len(code) == 6 and code.isdigit()):
        return _error("invalid_code", "Enter the 6-digit verification code", 400)

    ok, token_or_err, states = verify_otp(email, code)
    if not ok:
        status_map = {
            "invalid_code": (400, "Invalid verification code"),
            "code_expired": (400, "Verification code expired; request a new one"),
            "too_many_attempts": (400, "Too many attempts; request a new code"),
        }
        http_status, message = status_map.get(
            token_or_err or "", (400, "Verification failed")
        )
        return _error(token_or_err or "invalid_code", message, http_status)

    return jsonify(
        {
            "ok": True,
            "sessionToken": token_or_err,
            "email": email,
            "states": states,
        }
    )


@subscriptions_bp.post("/verify-link")
def verify_link():
    """Exchange a one-time magic-link token for a manage session."""
    if not subscriptions_enabled():
        return _feature_off()
    body = request.get_json(silent=True) or {}
    magic = str(body.get("token") or body.get("magicToken") or "").strip()
    ok, token_or_err, email, states = verify_magic_link(magic)
    if not ok:
        status_map = {
            "invalid_link": (400, "This manage link is invalid or already used"),
            "link_expired": (400, "This manage link expired; request a new one"),
        }
        http_status, message = status_map.get(
            token_or_err or "", (400, "Could not verify manage link")
        )
        return _error(token_or_err or "invalid_link", message, http_status)
    return jsonify(
        {
            "ok": True,
            "sessionToken": token_or_err,
            "email": email,
            "states": states,
        }
    )


@subscriptions_bp.get("/me")
def me():
    if not subscriptions_enabled():
        return _feature_off()
    email, err = _session_email_from_request()
    if err:
        return err
    return jsonify(
        {
            "email": email,
            "states": get_states(email),
            "monthlyDigest": get_monthly_digest(email),
        }
    )


@subscriptions_bp.post("/monthly")
def signup_monthly():
    """Opt into the tracker-wide monthly digest (no OTP; in-UI confirmation)."""
    if not subscriptions_enabled():
        return _feature_off()
    body = request.get_json(silent=True) or {}
    email = normalize_email(str(body.get("email") or ""))
    if not is_valid_email(email):
        return _error("invalid_email", "A valid email address is required", 400)

    rate_key = f"monthly|{_client_ip()}|{email}"
    if _rate_limited(rate_key):
        return _error("rate_limited", "Too many requests; try again later", 429)

    already = get_monthly_digest(email)
    set_monthly_digest(email, True)
    if already:
        message = "You're already subscribed to the monthly digest."
    else:
        message = "You're subscribed to the monthly MMIP policy digest."
    return jsonify(
        {
            "ok": True,
            "status": "subscribed",
            "email": email,
            "monthlyDigest": True,
            "added": not already,
            "alreadySubscribed": already,
            "message": message,
        }
    )


@subscriptions_bp.post("/subscribe")
def subscribe():
    if not subscriptions_enabled():
        return _feature_off()
    email, err = _session_email_from_request()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    state = _normalize_subscribable_state(body.get("state"))
    if not state:
        return _error("invalid_state", "A valid state code is required", 400)
    states = add_state(email, state)
    return jsonify({"ok": True, "email": email, "states": states, "added": state})


@subscriptions_bp.post("/unsubscribe")
def unsubscribe():
    if not subscriptions_enabled():
        return _feature_off()
    email, err = _session_email_from_request()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    remove_all = bool(body.get("all")) or str(body.get("state") or "").lower() == "all"
    state = None
    if not remove_all:
        state = _normalize_subscribable_state(body.get("state"))
        if not state:
            return _error(
                "invalid_state",
                "Provide a valid state code or set all=true",
                400,
            )
    states = remove_state(email, state, remove_all=remove_all)
    return jsonify(
        {
            "ok": True,
            "email": email,
            "states": states,
            "removed": "all" if remove_all else state,
        }
    )
