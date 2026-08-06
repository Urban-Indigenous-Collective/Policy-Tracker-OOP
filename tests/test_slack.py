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


def test_slack_quiet_run_no_notification(monkeypatch):
    monkeypatch.setenv("DISCOVERY_SLACK_ALWAYS", "false")
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", quiet_runs=True)
    with patch.object(notifier, "_post", return_value=True) as mock_post:
        result = notifier.notify_run_complete(analyzed=0, rejected=5, skipped=10, errors=0)
        assert result is False
        mock_post.assert_not_called()


def test_slack_always_posts_empty_run_summary(monkeypatch):
    monkeypatch.setenv("DISCOVERY_SLACK_ALWAYS", "true")
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", quiet_runs=True)
    with patch.object(notifier, "_post", return_value=True) as mock_post:
        result = notifier.notify_run_complete(
            analyzed=0, rejected=0, skipped=194, errors=0, discovered=194
        )
        assert result is True
        mock_post.assert_called_once()
        text = mock_post.call_args[0][0]["text"]
        assert "194 discovered" in text
        assert "194 skipped" in text


def test_slack_status_change_batch():
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", quiet_runs=False)
    items = [
        {
            "title": f"Bill {i}",
            "state": "VT",
            "table": "Live",
            "source_url": f"https://legiscan.com/VT/bill/HB{i}/2026",
            "changes": [{"field": "Status", "old": "Pending", "new": "Passed"}],
        }
        for i in range(3)
    ]
    with patch.object(notifier, "_post", return_value=True) as mock_post:
        notifier.notify_status_changes(items)
        mock_post.assert_called_once()
        payload = mock_post.call_args[0][0]
        assert "3 bill status updates" in payload["blocks"][0]["text"]["text"]


def test_slack_status_change_batch_chunks_long_messages():
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", quiet_runs=False)
    items = [
        {
            "title": "X" * 200,
            "state": "VT",
            "table": "Live",
            "source_url": "https://legiscan.com/VT/bill/HB1/2026",
            "changes": [
                {
                    "field": "Chamber Details",
                    "old": "A" * 200,
                    "new": "B" * 200,
                }
            ],
        }
        for _ in range(20)
    ]
    with patch.object(notifier, "_post", return_value=True) as mock_post:
        ok = notifier.notify_status_changes(items)
        assert ok is True
        assert mock_post.call_count >= 2
        for call in mock_post.call_args_list:
            section_text = call.args[0]["blocks"][1]["text"]["text"]
            assert len(section_text) <= 3000


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
