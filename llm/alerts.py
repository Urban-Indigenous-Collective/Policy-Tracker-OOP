"""Slack + email alerts when the production LLM is unreachable."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from llm.health import LlmHealthResult, probe_llm

logger = logging.getLogger(__name__)


DEFAULT_ALERT_EMAIL = "austin@urbanindigenouscollective.org"


def alert_email() -> str:
    return (
        os.getenv("LLM_ALERT_EMAIL")
        or os.getenv("OPS_ALERT_EMAIL")
        or DEFAULT_ALERT_EMAIL
    ).strip()


def _state_path() -> Path:
    db_path = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
    return db_path.parent / "llm_alert_state.json"


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _day_key(checked_at: str) -> str:
    # ISO timestamps → YYYY-MM-DD (UTC date is fine for dedupe).
    return (checked_at or "")[:10] or "unknown"


def format_llm_down_message(result: LlmHealthResult, *, when: str = "nightly probe") -> str:
    return (
        f"LLM unreachable during {when}. "
        f"base={result.base_url} model={result.model} "
        f"latency_ms={result.latency_ms} error={result.error or 'unknown'}. "
        "Discovery will crawl but cannot analyze new candidates until the model is back."
    )


def notify_llm_down_slack(
    result: LlmHealthResult,
    *,
    when: str = "nightly probe",
    slack: Any | None = None,
) -> bool:
    from slack_client import SlackNotifier

    notifier = slack or SlackNotifier()
    return notifier.notify_error(format_llm_down_message(result, when=when))


def notify_llm_down_email(
    result: LlmHealthResult,
    *,
    when: str = "nightly probe",
    force: bool = False,
) -> bool:
    """Email ops once per UTC day while the LLM stays down (unless force=True)."""
    to = alert_email()
    if not to:
        logger.info("LLM alert email skipped (LLM_ALERT_EMAIL / OPS_ALERT_EMAIL unset)")
        return False

    day = _day_key(result.checked_at)
    state = _load_state()
    if not force and state.get("last_email_day") == day and state.get("last_email_ok") is False:
        logger.info("LLM alert email already sent for %s; skipping duplicate", day)
        return False

    subject = "MMIP Policy Tracker: LLM is down"
    body = (
        f"<p><strong>The Policy Tracker LLM is unreachable.</strong></p>"
        f"<p>{format_llm_down_message(result, when=when)}</p>"
        f"<p>Checked at: {result.checked_at or 'n/a'}</p>"
        f"<p>Quiet Slack heartbeats (0 analyzed / all skipped) can hide this — "
        f"fix llama-server / Ollama on the UIC host.</p>"
    )
    try:
        from subscriptions.mail import MailDeliveryError, send_email

        send_email(to=to, subject=subject, html=body)
    except MailDeliveryError:
        logger.exception("LLM alert email delivery failed to=%s", to)
        return False
    except Exception:
        logger.exception("LLM alert email unexpected failure to=%s", to)
        return False

    state["last_email_day"] = day
    state["last_email_ok"] = False
    state["last_error"] = result.error
    _save_state(state)
    logger.info("LLM alert email sent to=%s day=%s", to, day)
    return True


def clear_llm_alert_state_on_recovery(result: LlmHealthResult) -> None:
    """Allow a fresh email the next time the LLM dies."""
    if not result.ok:
        return
    state = _load_state()
    if not state:
        return
    state["last_email_ok"] = True
    state["last_recovered_at"] = result.checked_at
    _save_state(state)


def check_and_alert_llm(
    *,
    when: str = "nightly probe",
    slack: Any | None = None,
    send_email_alert: bool = True,
    send_slack_alert: bool = True,
) -> LlmHealthResult:
    """Probe LLM; on failure notify Slack and (once/day) email."""
    result = probe_llm()
    if result.ok:
        clear_llm_alert_state_on_recovery(result)
        return result
    if send_slack_alert:
        notify_llm_down_slack(result, when=when, slack=slack)
    if send_email_alert:
        notify_llm_down_email(result, when=when)
    return result
