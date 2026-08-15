"""Tests for USAO listing URL selection in federal bootstrap."""

from scripts.bootstrap_federal_sources import (
    infer_usao_listing_from_seed,
    probe_listing_url,
)


def test_infer_usao_listing_from_pr_deep_link():
    url = infer_usao_listing_from_seed(
        [
            "https://www.justice.gov/usao-ak/pr/pilot-projects-launched-address-missing-and-murdered-indigenous-persons"
        ],
        "usao-ak",
    )
    assert url == "https://www.justice.gov/usao-ak/pr"


def test_infer_usao_listing_ignores_file_download_seed():
    url = infer_usao_listing_from_seed(
        ["https://www.justice.gov/usao-or/page/file/1368976/download"],
        "usao-or",
    )
    assert url is None


def test_probe_listing_url_never_returns_homepage(monkeypatch):
    import scripts.bootstrap_federal_sources as mod

    class FakeResp:
        def __init__(self, url, status, body):
            self.url = url
            self.status_code = status
            self.text = body

    calls = []

    def fake_get(url, headers=None, timeout=12, allow_redirects=True):
        calls.append(url)
        if url.endswith("/pr"):
            return FakeResp(url, 200, "x" * 100)
        if url.endswith("/news"):
            return FakeResp(url, 200, "y" * 50_000)  # longer — must not win solely on size
        return FakeResp(url, 404, "")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    best, status, note = probe_listing_url("usao-ak")
    assert best.endswith("/usao-ak/pr")
    assert status == 200
    assert note == "probed"
    assert calls[0].endswith("/pr")
