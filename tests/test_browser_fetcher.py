"""Browser fetcher availability and graceful degradation."""

import builtins
import sys

from discovery.browser_fetcher import BrowserRenderer


def test_browser_start_returns_false_when_playwright_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api" or name.startswith("playwright"):
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    renderer = BrowserRenderer("test-agent")
    assert renderer.start() is False
    assert renderer.available is False
    assert "Playwright is required" in renderer._unavailable_reason
    assert renderer.fetch("https://example.gov/mmip") == ("", "")


def test_federal_discover_skips_render_js_when_playwright_missing(monkeypatch):
    from discovery.federal_crawler import FederalSiteSource
    from discovery.federal_schema import FederalSource

    source = FederalSiteSource()
    render_js = FederalSource(
        source_id="fed-test-js",
        name="JS Test",
        url="https://example.gov/mmip",
        method="index",
        content_type="press_release",
        render_js=True,
    )
    plain = FederalSource(
        source_id="fed-test-plain",
        name="Plain Test",
        url="https://example.gov/plain",
        method="index",
        content_type="press_release",
        render_js=False,
    )

    monkeypatch.setattr(source, "load_sources", lambda: [render_js, plain])
    monkeypatch.setattr(source.browser, "start", lambda: False)
    source.browser._unavailable_reason = "Playwright missing in test"

    class FakeIndexFetcher:
        def discover(self, src):
            yield from ()

    source.index_fetcher = FakeIndexFetcher()

    discovered = list(source.discover())
    assert discovered == []
