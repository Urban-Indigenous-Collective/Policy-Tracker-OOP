"""LLM health probe + ops alerts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from llm.alerts import (
    check_and_alert_llm,
    format_llm_down_message,
    notify_llm_down_email,
)
from llm.health import LlmHealthResult, probe_llm


def test_probe_llm_ok(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen-test")
    monkeypatch.setenv("LLM_API_KEY", "ollama")

    listed = MagicMock()
    listed.data = [MagicMock(id="qwen-test")]

    with patch("openai.OpenAI") as client_cls:
        client_cls.return_value.models.list.return_value = listed
        result = probe_llm(timeout_sec=1)

    assert result.ok is True
    assert result.base_url == "http://llm.test/v1"
    assert result.model == "qwen-test"
    assert result.error == ""


def test_probe_llm_failure(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen-test")

    with patch("openai.OpenAI") as client_cls:
        client_cls.return_value.models.list.side_effect = ConnectionError("reset")
        result = probe_llm(timeout_sec=1)

    assert result.ok is False
    assert "ConnectionError" in result.error
    assert "unreachable" in format_llm_down_message(result).lower() or "LLM" in format_llm_down_message(result)


def test_check_and_alert_notifies_slack_and_email(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    monkeypatch.delenv("LLM_ALERT_EMAIL", raising=False)
    monkeypatch.delenv("OPS_ALERT_EMAIL", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen-test")

    bad = LlmHealthResult(
        ok=False,
        base_url="http://llm.test/v1",
        model="qwen-test",
        error="timeout",
        checked_at="2026-11-11T07:00:00+00:00",
    )
    slack = MagicMock()
    slack.notify_error.return_value = True

    with (
        patch("llm.alerts.probe_llm", return_value=bad),
        patch("subscriptions.mail.send_email") as send_email,
    ):
        out = check_and_alert_llm(when="unit test", slack=slack)
        assert out.ok is False
        slack.notify_error.assert_called_once()
        send_email.assert_called_once()
        assert send_email.call_args.kwargs["to"] == "austin@urbanindigenouscollective.org"
        assert "LLM is down" in send_email.call_args.kwargs["subject"]

        # Same UTC day → email deduped
        send_email.reset_mock()
        notify_llm_down_email(bad, when="unit test again")
        send_email.assert_not_called()
