"""BrowserRenderer must wait out soft bm-verify challenges instead of early-exiting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from discovery.browser_fetcher import BrowserRenderer


SOFT_SHELL = (
    "<!DOCTYPE html><html><head>"
    "<meta http-equiv=\"refresh\" content=\"5; URL='/pr?bm-verify=AAQ'\">"
    "<title>\xa0</title></head><body></body></html>"
)
REAL_HTML = (
    "<html><head><title>Real Press Release</title></head>"
    "<body><h1>Real Press Release</h1>"
    "<article>Missing and Murdered Indigenous Persons strategy details.</article>"
    "</body></html>"
)


def test_fetch_waits_out_soft_challenge_then_returns_content():
    renderer = BrowserRenderer("Mozilla/5.0 test")
    renderer._browser = MagicMock()  # mark as started

    page = MagicMock()
    context = MagicMock()
    page.content.side_effect = [SOFT_SHELL, REAL_HTML]
    page.goto.return_value = None

    with patch.object(renderer, "_new_page", return_value=(context, page)):
        with patch.object(renderer, "_wait_out_soft_challenge") as wait_soft:
            html, content_hash = renderer.fetch(
                "https://www.justice.gov/opa/pr/example",
                wait_selector="h1, article",
                settle_ms=0,
            )

    wait_soft.assert_called_once()
    page.wait_for_selector.assert_called_once()
    assert "Real Press Release" in html
    assert content_hash
    context.close.assert_called_once()


def test_fetch_hard_deny_returns_empty_without_waiting():
    renderer = BrowserRenderer("Mozilla/5.0 test")
    renderer._browser = MagicMock()

    deny = (
        "<html><head><title>Access Denied</title></head>"
        "<body>You don't have permission to access "
        "\"http://www.justice.gov/x\" on this server."
        "<p>https://errors.edgesuite.net/18.abc</p></body></html>"
    )
    page = MagicMock()
    context = MagicMock()
    page.content.return_value = deny

    with patch.object(renderer, "_new_page", return_value=(context, page)):
        with patch.object(renderer, "_wait_out_soft_challenge") as wait_soft:
            html, content_hash = renderer.fetch(
                "https://www.justice.gov/opa/pr/example",
                wait_selector="h1",
            )

    wait_soft.assert_not_called()
    assert html == ""
    assert content_hash == ""
