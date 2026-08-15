"""Regression: crawlers must extract PDF text, not parse binary as HTML."""

from discovery.queries import keyword_prescreen
from discovery.site_crawler import StateSiteSource

NM_MMIWR_EXCERPT = (
    "New Mexico Missing and Murdered Indigenous Women and Relatives TASK FORCE REPORT. "
    "Report to the Governor and Legislature on the Task Force Findings and "
    "Recommendations. MMIWR data collection and law enforcement coordination."
)


class FakeContentHttp:
    def fetch_content(self, url, verify=True, ignore_robots=False, user_agent=""):
        return b"%PDF-1.4\n% fake bytes", "pdfhash", "application/pdf"


def test_state_site_fetch_page_text_uses_pdf_extractor(monkeypatch):
    """NM IAD PDFs were false-rejected when fetch_page_text parsed PDF bytes as HTML."""
    source = StateSiteSource()
    source.http = FakeContentHttp()

    def fake_extract(content, url, content_type=""):
        assert content.startswith(b"%PDF")
        assert url.endswith(".pdf")
        return NM_MMIWR_EXCERPT

    monkeypatch.setattr("discovery.fetchers.extract_document_text", fake_extract)

    text, content_hash = source.fetch_page_text(
        "https://www.iad.nm.gov/wp-content/uploads/2020/12/NM_MMIWR_Report_FINAL_WEB_v120920.pdf"
    )

    assert content_hash == "pdfhash"
    assert keyword_prescreen(text)
    assert "Missing and Murdered Indigenous" in text
    assert not text.startswith("%PDF")


def test_state_site_fetch_page_text_html_still_works(monkeypatch):
    html = b"""
    <html><body><main>
    <h1>Missing and Murdered Indigenous Persons Clearinghouse</h1>
    <p>The clearinghouse supports families of missing Indigenous relatives.</p>
    </main></body></html>
    """

    class HtmlHttp:
        def fetch_content(self, url, verify=True, ignore_robots=False, user_agent=""):
            return html, "htmlhash", "text/html"

    source = StateSiteSource()
    source.http = HtmlHttp()
    text, content_hash = source.fetch_page_text("https://example.gov/mmip-clearinghouse/")
    assert content_hash == "htmlhash"
    assert keyword_prescreen(text)
    assert "Missing and Murdered Indigenous Persons" in text


def test_federal_site_fetch_page_text_uses_fr_api(monkeypatch):
    from discovery.federal_crawler import FederalSiteSource

    fr_url = (
        "https://www.federalregister.gov/documents/2024/05/13/"
        "2024-10533/missing-or-murdered-indigenous-persons-awareness-day-2024"
    )
    source = FederalSiteSource()

    def fake_fetch_fr(http, url):
        assert url == fr_url
        return (
            "Missing or Murdered Indigenous Persons Awareness Day, 2024. "
            "Presidential proclamation recognizing missing indigenous relatives.",
            "frhash",
        )

    monkeypatch.setattr("discovery.fetchers.fetch_federal_register_document_text", fake_fetch_fr)

    text, content_hash = source.fetch_page_text(fr_url)
    assert content_hash == "frhash"
    assert keyword_prescreen(text)
    assert "Missing or Murdered Indigenous Persons" in text


def test_federal_site_fetch_page_text_justice_bot_wall_fallback(monkeypatch):
    """HTTP Akamai wall on /usao-*/pr/* must fall back to Playwright."""
    from discovery.federal_crawler import FederalSiteSource

    bot_wall = (
        "<html><head><title>Access Denied</title></head>"
        "<body>You don't have permission to access "
        '"http://www.justice.gov/usao-ak/pr/mmip-test" on this server.</body></html>'
    ).encode()
    good_html = (
        "<html><body><main>"
        "<p>United States Attorney announces Missing and Murdered Indigenous Persons "
        "initiative and tribal coordination.</p>"
        "</main></body></html>"
    ).encode()

    class BotHttp:
        def fetch_content(self, url, verify=True, ignore_robots=False, user_agent=""):
            return bot_wall, "badhash", "text/html"

    class FakeBrowser:
        def fetch(self, url, **kwargs):
            assert "justice.gov" in url
            return good_html.decode(), "goodhash"

    source = FederalSiteSource()
    source.http = BotHttp()
    source.browser = FakeBrowser()

    text, content_hash = source.fetch_page_text(
        "https://www.justice.gov/usao-ak/pr/mmip-test"
    )
    assert content_hash == "goodhash"
    assert keyword_prescreen(text)
    assert "Missing and Murdered Indigenous Persons" in text


def test_state_site_fetch_page_text_mass_gov_bot_wall_fallback(monkeypatch):
    """mass.gov EO document pages 403 on HTTP; analysis must use Playwright."""
    bot_wall = b""
    good_html = (
        "<html><body><main>"
        "<h1>No. 604: Establishing the Office Of Climate Innovation</h1>"
        "<p>Executive order establishing climate resilience coordination.</p>"
        "</main></body></html>"
    ).encode()

    class EmptyHttp:
        def fetch_content(self, url, verify=True, ignore_robots=False, user_agent=""):
            return bot_wall, "", ""

    class FakeBrowser:
        def fetch(self, url, **kwargs):
            assert "mass.gov" in url
            return good_html.decode(), "goodhash"

    source = StateSiteSource()
    source.http = EmptyHttp()
    source.browser = FakeBrowser()

    text, content_hash = source.fetch_page_text(
        "https://www.mass.gov/executive-orders/no-604-establishing-the-office-of-climate-innovation-and-resilience-within-the-office-of-the-governor"
    )
    assert content_hash == "goodhash"
    assert "Climate Innovation" in text


def test_fetch_justice_gov_content_empty_extract_triggers_browser():
    from discovery.fetchers import HttpFetcher, fetch_justice_gov_content

    shell_html = b"<html><body><nav>Department of Justice</nav></body></html>"
    article_html = (
        "<html><body><p>Missing and Murdered Indigenous Persons task force update.</p></body></html>"
    ).encode()

    class ShellHttp:
        def fetch_content(self, url, verify=True, ignore_robots=False, user_agent=""):
            return shell_html, "shellhash", "text/html"

    class FakeBrowser:
        def fetch(self, url, **kwargs):
            return article_html.decode(), "articlehash"

        def stop(self):
            pass

    body, content_hash, content_type = fetch_justice_gov_content(
        ShellHttp(),
        "https://www.justice.gov/usao-nm/pr/mmip-update",
        browser=FakeBrowser(),
    )
    assert content_hash == "articlehash"
    assert content_type == "text/html"
    assert b"Missing and Murdered Indigenous Persons" in body

