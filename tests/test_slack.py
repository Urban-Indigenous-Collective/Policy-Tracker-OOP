from unittest.mock import patch

from slack_client import SlackNotifier


def test_slack_discovery_blocks_structure():
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", quiet_runs=False)
    with patch.object(notifier, "_post", return_value=True) as mock_post:
        notifier.notify_discovery(
            state="NM",
            title="MMIP Task Force Act",
            summary="Establishes a task force for missing Indigenous persons.",
            categories="Taskforce, MMIP Relatives",
            confidence=0.92,
            source_url="https://legiscan.com/NM/bill/SB123/2025",
        )
        mock_post.assert_called_once()
        payload = mock_post.call_args[0][0]
        assert "blocks" in payload
        assert payload["blocks"][0]["type"] == "header"
        assert "MMIP Task Force Act" in payload["blocks"][1]["text"]["text"]


def test_slack_quiet_run_no_notification():
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", quiet_runs=True)
    with patch.object(notifier, "_post", return_value=True) as mock_post:
        result = notifier.notify_run_complete(analyzed=0, rejected=5, skipped=10, errors=0)
        assert result is False
        mock_post.assert_not_called()


def test_slack_batch_over_five():
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", quiet_runs=False)
    items = [
        {
            "state": "NM",
            "title": f"Bill {i}",
            "summary": "Summary",
            "categories": "Taskforce",
            "confidence": 0.9,
            "source_url": f"https://example.com/{i}",
        }
        for i in range(6)
    ]
    with patch.object(notifier, "_post", return_value=True) as mock_post:
        notifier.notify_discovery_batch(items)
        mock_post.assert_called_once()
        payload = mock_post.call_args[0][0]
        assert "6 new MMIP policies" in payload["blocks"][1]["text"]["text"]
