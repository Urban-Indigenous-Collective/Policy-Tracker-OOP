"""JSON-backed store for state subscription emails, OTPs, and verified sessions."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from subscriptions.config import (
    fixed_otp_for_tests,
    otp_ttl_seconds,
    session_ttl_seconds,
    store_path,
)

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_MAX_OTP_ATTEMPTS = 5


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _empty_payload() -> dict[str, Any]:
    return {
        "subscribers": {},
        "pending_otps": {},
        "sessions": {},
        "digest_notified": {},
    }


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_payload()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("state_subscribe store unreadable (%s); starting empty", exc)
        return _empty_payload()
    if not isinstance(data, dict):
        return _empty_payload()
    data.setdefault("subscribers", {})
    data.setdefault("pending_otps", {})
    data.setdefault("sessions", {})
    data.setdefault("digest_notified", {})
    return data


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    text = normalize_email(email)
    if "@" not in text or text.startswith("@") or text.endswith("@"):
        return False
    local, _, domain = text.partition("@")
    return bool(local) and "." in domain and " " not in text


def get_states(email: str) -> list[str]:
    key = normalize_email(email)
    with _lock:
        data = _load(store_path())
        entry = data["subscribers"].get(key) or {}
        states = entry.get("states") or []
        return sorted({str(s) for s in states})


def _purge_expired_sessions(data: dict[str, Any], now: float) -> None:
    expired = [
        t
        for t, s in data["sessions"].items()
        if float(s.get("expires_at") or 0) < now
    ]
    for t in expired:
        data["sessions"].pop(t, None)


def _issue_session(data: dict[str, Any], email: str, now: float) -> tuple[str, list[str]]:
    token = secrets.token_urlsafe(32)
    data["sessions"][token] = {
        "email": email,
        "expires_at": now + session_ttl_seconds(),
        "created_at": _utc_now_iso(),
    }
    _purge_expired_sessions(data, now)
    entry = data["subscribers"].get(email) or {}
    states = sorted({str(s) for s in (entry.get("states") or [])})
    return token, states


def create_otp(email: str, state: str) -> tuple[str, str]:
    """Create pending OTP + magic link token. Returns (code, magic_token)."""
    key = normalize_email(email)
    code = fixed_otp_for_tests() or f"{secrets.randbelow(1_000_000):06d}"
    magic = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        data = _load(store_path())
        data["pending_otps"][key] = {
            "code_hash": _hash_code(code),
            "magic_hash": _hash_code(magic),
            "state": state,
            "expires_at": now + otp_ttl_seconds(),
            "attempts": 0,
            "created_at": _utc_now_iso(),
        }
        _save(store_path(), data)
    return code, magic


def verify_otp(email: str, code: str) -> tuple[bool, str | None, list[str]]:
    """
    Verify OTP. On success returns (True, session_token, states).
    On failure returns (False, error_code, []).
    """
    key = normalize_email(email)
    raw = str(code or "").strip()
    now = time.time()
    with _lock:
        data = _load(store_path())
        pending = data["pending_otps"].get(key)
        if not pending:
            return False, "invalid_code", []
        if float(pending.get("expires_at") or 0) < now:
            data["pending_otps"].pop(key, None)
            _save(store_path(), data)
            return False, "code_expired", []
        attempts = int(pending.get("attempts") or 0)
        if attempts >= _MAX_OTP_ATTEMPTS:
            data["pending_otps"].pop(key, None)
            _save(store_path(), data)
            return False, "too_many_attempts", []
        if _hash_code(raw) != pending.get("code_hash"):
            pending["attempts"] = attempts + 1
            data["pending_otps"][key] = pending
            _save(store_path(), data)
            return False, "invalid_code", []

        data["pending_otps"].pop(key, None)
        token, states = _issue_session(data, key, now)
        _save(store_path(), data)
        return True, token, states


def verify_magic_link(magic_token: str) -> tuple[bool, str | None, str | None, list[str]]:
    """
    Consume a one-time magic link token.
    On success: (True, session_token, email, states).
    On failure: (False, error_code, None, []).
    """
    raw = str(magic_token or "").strip()
    if not raw:
        return False, "invalid_link", None, []
    magic_hash = _hash_code(raw)
    now = time.time()
    with _lock:
        data = _load(store_path())
        match_email = None
        for email, pending in list(data["pending_otps"].items()):
            if pending.get("magic_hash") == magic_hash:
                match_email = email
                break
        if not match_email:
            return False, "invalid_link", None, []
        pending = data["pending_otps"][match_email]
        if float(pending.get("expires_at") or 0) < now:
            data["pending_otps"].pop(match_email, None)
            _save(store_path(), data)
            return False, "link_expired", None, []
        data["pending_otps"].pop(match_email, None)
        token, states = _issue_session(data, match_email, now)
        _save(store_path(), data)
        return True, token, match_email, states


def resolve_session(token: str) -> str | None:
    """Return normalized email for a valid session token, else None."""
    raw = str(token or "").strip()
    if not raw:
        return None
    now = time.time()
    with _lock:
        data = _load(store_path())
        session = data["sessions"].get(raw)
        if not session:
            return None
        if float(session.get("expires_at") or 0) < now:
            data["sessions"].pop(raw, None)
            _save(store_path(), data)
            return None
        return str(session.get("email") or "") or None


def add_state(email: str, state: str) -> list[str]:
    key = normalize_email(email)
    now = _utc_now_iso()
    with _lock:
        data = _load(store_path())
        entry = data["subscribers"].get(key) or {
            "states": [],
            "created_at": now,
        }
        states = {str(s) for s in (entry.get("states") or [])}
        states.add(state)
        entry["states"] = sorted(states)
        entry["updated_at"] = now
        entry.setdefault("created_at", now)
        data["subscribers"][key] = entry
        _save(store_path(), data)
        return list(entry["states"])


def remove_state(email: str, state: str | None, *, remove_all: bool = False) -> list[str]:
    key = normalize_email(email)
    now = _utc_now_iso()
    with _lock:
        data = _load(store_path())
        entry = data["subscribers"].get(key)
        if not entry:
            return []
        if remove_all:
            entry["states"] = []
        else:
            states = {str(s) for s in (entry.get("states") or [])}
            if state:
                states.discard(state)
            entry["states"] = sorted(states)
        entry["updated_at"] = now
        if entry["states"]:
            data["subscribers"][key] = entry
        else:
            # Keep empty record so "existing email" manage UX can still find history,
            # but drop if never had meaningful data — keep empty list for simplicity.
            data["subscribers"][key] = entry
        _save(store_path(), data)
        return list(entry.get("states") or [])


def list_subscribers() -> list[tuple[str, list[str]]]:
    """Return (email, states) for every subscriber with at least one state."""
    with _lock:
        data = _load(store_path())
        out: list[tuple[str, list[str]]] = []
        for email, entry in (data.get("subscribers") or {}).items():
            states = sorted(
                {str(s) for s in (entry or {}).get("states") or [] if str(s).strip()}
            )
            if states:
                out.append((str(email), states))
        return out


def filter_unnotified_digest_keys(keys: list[str]) -> list[str]:
    """Return keys that have not yet been marked notified."""
    wanted = [str(k) for k in keys if k]
    if not wanted:
        return []
    with _lock:
        data = _load(store_path())
        notified = data.get("digest_notified") or {}
        return [k for k in wanted if k not in notified]


def mark_digest_notified(keys: list[str] | set[str]) -> None:
    """Record digest event keys as sent (idempotency watermark)."""
    now = _utc_now_iso()
    incoming = {str(k) for k in keys if k}
    if not incoming:
        return
    with _lock:
        data = _load(store_path())
        notified = dict(data.get("digest_notified") or {})
        for key in incoming:
            notified[key] = now
        # Cap growth: keep the most recent ~5000 keys
        if len(notified) > 5000:
            ordered = sorted(notified.items(), key=lambda kv: kv[1])
            notified = dict(ordered[-4000:])
        data["digest_notified"] = notified
        _save(store_path(), data)


def reset_store_for_tests(path: Path | None = None) -> None:
    """Wipe store file used in tests."""
    target = path or store_path()
    with _lock:
        if target.exists():
            target.unlink()
        sibling = target.with_suffix(target.suffix + ".tmp")
        if sibling.exists():
            sibling.unlink()
