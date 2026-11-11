"""Feature flags and tunables for state subscriptions."""

from __future__ import annotations

import os
from pathlib import Path


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


def subscriptions_enabled() -> bool:
    return _env_flag("STATE_SUBSCRIBE_ENABLED", "false")


def store_path() -> Path:
    raw = (os.getenv("STATE_SUBSCRIBE_STORE_PATH") or "data/state_subscriptions.json").strip()
    return Path(raw)


def otp_ttl_seconds() -> int:
    try:
        return max(60, int(os.getenv("STATE_SUBSCRIBE_OTP_TTL_SECONDS", "600")))
    except ValueError:
        return 600


def session_ttl_seconds() -> int:
    try:
        return max(60, int(os.getenv("STATE_SUBSCRIBE_SESSION_TTL_SECONDS", "1800")))
    except ValueError:
        return 1800


def fixed_otp_for_tests() -> str | None:
    """When set, request-code uses this 6-digit code (tests / local only)."""
    raw = (os.getenv("STATE_SUBSCRIBE_FIXED_OTP") or "").strip()
    if len(raw) == 6 and raw.isdigit():
        return raw
    return None


def request_code_rate_limit() -> tuple[int, int]:
    """Return (max_requests, window_seconds) for request-code throttling."""
    try:
        max_requests = max(1, int(os.getenv("STATE_SUBSCRIBE_RATE_MAX", "5")))
    except ValueError:
        max_requests = 5
    try:
        window = max(30, int(os.getenv("STATE_SUBSCRIBE_RATE_WINDOW_SECONDS", "600")))
    except ValueError:
        window = 600
    return max_requests, window
