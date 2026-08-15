"""Tests for state site fetchers."""

import hashlib
import json

import pytest

from discovery.browser_fetcher import looks_like_bot_wall
from discovery.fetchers import (
    ApiFetcher,
    HttpFetcher,
    IndexFetcher,
    RssFetcher,
    SearchFetcher,
    anchor_text_is_weak,
    bump_page_url,
    current_page_number,
    extract_table_document_links,
    next_page_url,
    year_slug_probe_range,
)
from discovery.source_schema import StateSource


def test_looks_like_bot_wall_akamai_interstitial():
    html = (
        "<!DOCTYPE html><html><head>"
        "<meta http-equiv=\"refresh\" content=\"5; URL='/usao-ak/pr?bm-verify=AAQAAA'\">"
        "</head><body></body></html>"
    )
    assert looks_like_bot_wall(html) is True


def test_looks_like_bot_wall_access_denied():
    html = (
        "<html><head><title>Access Denied</title></head>"
        "<body><h1>Access Denied</h1>"
        "You don't have permission to access "
        "\"http://www.justice.gov/usao-ak/pr\" on this server."
        "<p>https://errors.edgesuite.net/18.cd623417</p></body></html>"
    )
    assert looks_like_bot_wall(html) is True


def test_looks_like_bot_wall_real_page():
    html = "<html><body>" + ("press release " * 500) + "</body></html>"
    assert looks_like_bot_wall(html) is False


HTML = """
<html><body>
  <a href="/news/mmip-task-force">MMIP Task Force established for tribal communities</a>
  <a href="https://other.gov/page">Other</a>
</body></html>
"""

RSS = """<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>Missing indigenous persons awareness day</title>
    <link>https://example.gov/pr/1</link>
    <description>Proclamation for missing and murdered indigenous peoples</description>
  </item>
</channel></rss>"""


class FakeHttp(HttpFetcher):
    def __init__(self, pages: dict[str, str]):
        super().__init__("test-agent", per_domain_delay=0)
        self.pages = pages

    def fetch(
        self,
        url: str,
        method: str = "GET",
        data=None,
        verify=True,
        ignore_robots=False,
        user_agent: str = "",
    ):
        body = self.pages.get(url, "")
        return body, hashlib.sha256(body.encode()).hexdigest(), url


def test_index_fetcher_prescreens_mmip_links():
    http = FakeHttp({"https://gov.example.gov/news": HTML})
    source = StateSource(
        state="EX",
        name="Example news",
        method="index",
        url="https://gov.example.gov/news",
    )
    candidates = list(IndexFetcher(http).discover(source))
    assert len(candidates) == 1
    assert "mmip" in candidates[0].title.lower()


def test_index_fetcher_skips_javascript_hrefs():
    html = """
    <html><body>
      <a href="javascript:void(0)">MMIP Task Force fake link</a>
      <a href="/real/mmiw-report">MMIW report for indigenous communities</a>
    </body></html>
    """
    http = FakeHttp({"https://gov.example.gov/news": html})
    source = StateSource(
        state="EX",
        name="Example news",
        method="index",
        url="https://gov.example.gov/news",
    )
    candidates = list(IndexFetcher(http).discover(source))
    assert len(candidates) == 1
    assert candidates[0].url.endswith("/real/mmiw-report")


def test_index_fetcher_does_not_prescreen_via_source_name():
    """Listing pages named '... MMIP ...' must not admit unrelated nav links."""
    html = """
    <html><body>
      <a href="/home">Home</a>
      <a href="/about">Programs</a>
      <a href="/reports/mmip-response-plan">MMIP State Response Plan</a>
    </body></html>
    """
    http = FakeHttp({"https://iad.example.gov/mmip/": html})
    source = StateSource(
        state="EX",
        name="Example MMIP program hub",
        method="index",
        url="https://iad.example.gov/mmip/",
        link_selector="a",
    )
    candidates = list(IndexFetcher(http).discover(source))
    assert len(candidates) == 1
    assert candidates[0].url.endswith("/reports/mmip-response-plan")


def test_index_fetcher_yields_sample_urls():
    http = FakeHttp({"https://gov.example.gov/pr": "<html><body></body></html>"})
    source = StateSource(
        state="EX",
        name="USAO Example",
        method="index",
        url="https://gov.example.gov/pr",
        sample_urls=[
            "https://gov.example.gov/pr/pilot-projects-missing-and-murdered-indigenous-persons",
        ],
    )
    candidates = list(IndexFetcher(http).discover(source))
    assert len(candidates) == 1
    assert "missing-and-murdered-indigenous" in candidates[0].url


def test_year_slug_probe_range_includes_recent_years():
    years = list(year_slug_probe_range(back_years=3))
    assert years[0] == 2026
    assert len(years) == 4


def test_index_fetcher_yields_year_slug_probes():
    proc_2023 = """
    <html><body>
      <h1>Day of Awareness for Missing and Murdered Indigenous Women</h1>
      <p>Proclamation for missing and murdered indigenous women awareness day.</p>
    </body></html>
    """
    http = FakeHttp(
        {
            "https://gov.example.gov/news/procs": "<html><body></body></html>",
            "https://gov.example.gov/governor-proclaims-mmip-awareness-2023": proc_2023,
            "https://gov.example.gov/governor-proclaims-mmip-awareness-2022": "",
            "https://gov.example.gov/governor-proclaims-mmip-awareness-2021": "",
            "https://gov.example.gov/governor-proclaims-mmip-awareness-2024": "",
            "https://gov.example.gov/governor-proclaims-mmip-awareness-2025": "",
            "https://gov.example.gov/governor-proclaims-mmip-awareness-2026": "",
        }
    )
    source = StateSource(
        state="EX",
        name="Example proclamations",
        method="index",
        url="https://gov.example.gov/news/procs",
        content_type="proclamation",
        year_slug_templates=[
            "https://gov.example.gov/governor-proclaims-mmip-awareness-{year}"
        ],
    )
    candidates = list(IndexFetcher(http).discover(source))
    assert len(candidates) == 1
    assert candidates[0].url.endswith("2023")


def test_search_fetcher_does_not_prescreen_via_query():
    """Unrelated titles must not pass just because the search query is MMIP-related."""
    html = """
    <html><body>
      <a href="https://gov.example.gov/page/1">Annual budget report</a>
      <a href="https://gov.example.gov/search?q=missing%20indigenous">Search again</a>
    </body></html>
    """
    http = FakeHttp({"https://gov.example.gov/search?q=missing%20indigenous": html})
    source = StateSource(
        state="EX",
        name="Example search",
        method="search",
        search_url="https://gov.example.gov/search?q={query}",
        search_queries=["missing indigenous"],
    )
    candidates = list(SearchFetcher(http).discover(source))
    assert candidates == []


def test_search_fetcher_prescreens_on_link_text():
    html = """
    <html><body>
      <a href="https://gov.example.gov/page/1">MMIP Task Force annual report</a>
      <a href="https://gov.example.gov/page/2">Annual budget report</a>
    </body></html>
    """
    http = FakeHttp({"https://gov.example.gov/search?q=MMIP": html})
    source = StateSource(
        state="EX",
        name="Example search",
        method="search",
        search_url="https://gov.example.gov/search?q={query}",
        search_queries=["MMIP"],
    )
    candidates = list(SearchFetcher(http).discover(source))
    assert len(candidates) == 1
    assert "mmip" in candidates[0].title.lower()
    assert "annual budget" not in candidates[0].title.lower()
    # Query may be noted for traceability after a real text match.
    assert "mmip" in candidates[0].snippet.lower()


def test_rss_fetcher_parses_items():
    http = FakeHttp({"https://gov.example.gov/feed.xml": RSS})
    source = StateSource(
        state="EX",
        name="Example RSS",
        method="rss",
        rss_url="https://gov.example.gov/feed.xml",
    )
    candidates = list(RssFetcher(http).discover(source))
    assert len(candidates) == 1
    assert "indigenous" in candidates[0].snippet.lower()


def test_api_fetcher_parses_open_legislation(monkeypatch):
    payload = {
        "success": True,
        "total": 1,
        "result": {
            "items": [
                {
                    "result": {
                        "session": 2023,
                        "basePrintNo": "S1234",
                        "title": "Establishes MMIP task force for indigenous communities",
                        "summary": "Missing and murdered indigenous persons awareness",
                    }
                }
            ]
        },
    }

    class FakeHttp(HttpFetcher):
        def fetch(
            self,
            url: str,
            method: str = "GET",
            data=None,
            verify=True,
            ignore_robots=False,
            user_agent: str = "",
        ):
            assert "MMIP" in url
            assert "test-key" in url
            return json.dumps(payload), "hash", url

    monkeypatch.setenv("NY_OPEN_LEGISLATION_KEY", "test-key")
    source = StateSource(
        state="NY",
        name="NY Open Leg",
        method="api",
        content_type="legislation",
        api_url_template="https://legislation.nysenate.gov/api/3/bills/search?term={query}&key={api_key}",
        api_key_env="NY_OPEN_LEGISLATION_KEY",
        search_queries=["MMIP"],
    )
    candidates = list(ApiFetcher(FakeHttp({})).discover(source))
    assert len(candidates) == 1
    assert candidates[0].url == "https://legislation.nysenate.gov/bills/2023/S1234"


def test_api_fetcher_parses_doj_press_releases():
    from discovery.federal_schema import FederalSource

    payload = {
        "metadata": {"responseInfo": {"status": 200}, "resultset": {"count": "1"}},
        "results": [
            {
                "title": "U.S. Attorney Joins MMIP Awareness Day for Indigenous Communities",
                "url": "https://www.justice.gov/usao-ak/pr/mmip-awareness-day",
                "teaser": "<p>Missing and murdered indigenous persons initiative</p>",
            }
        ],
    }
    http = FakeHttp(
        {
            "https://www.justice.gov/api/v1/press_releases.json"
            "?parameters[title]=MMIP&pagesize=20&sort=date&direction=DESC": json.dumps(payload)
        }
    )
    source = FederalSource.model_validate(
        {
            "name": "DOJ News API",
            "method": "api",
            "content_type": "press_release",
            "api_url_template": (
                "https://www.justice.gov/api/v1/press_releases.json"
                "?parameters[title]={query}&pagesize=20&sort=date&direction=DESC"
            ),
            "search_queries": ["MMIP"],
            "source_id": "fed-doj-news",
            "review_needed": False,
        }
    )
    candidates = list(ApiFetcher(http).discover(source))
    assert len(candidates) == 1
    assert candidates[0].url.endswith("/mmip-awareness-day")
    assert "indigenous" in (candidates[0].snippet or "").lower()


def test_api_fetcher_paginates_federal_register():
    from discovery.federal_schema import FederalSource

    page1 = {
        "count": 25,
        "next_page_url": (
            "https://www.federalregister.gov/api/v1/documents.json"
            "?conditions%5Btype%5D=PRESDOCU&conditions%5Bterm%5D=missing+indigenous&page=2"
        ),
        "results": [
            {
                "title": "Missing or Murdered Indigenous Persons Awareness Day, 2024",
                "html_url": (
                    "https://www.federalregister.gov/documents/2024/05/13/"
                    "2024-10533/missing-or-murdered-indigenous-persons-awareness-day-2024"
                ),
                "excerpts": (
                    "A Proclamation For decades, Native communities have faced "
                    "<span class=\"match\">missing</span> and murdered indigenous persons."
                ),
            }
        ],
    }
    page2 = {
        "count": 25,
        "results": [
            {
                "title": "Missing and Murdered Indigenous Persons Awareness Day, 2021",
                "html_url": (
                    "https://www.federalregister.gov/documents/2021/05/05/"
                    "2021-09654/missing-and-murdered-indigenous-persons-awareness-day-2021"
                ),
                "abstract": "Presidential proclamation for MMIP awareness day.",
            }
        ],
    }
    base = (
        "https://www.federalregister.gov/api/v1/documents.json"
        "?conditions[type]=PRESDOCU&conditions[term]=missing%20indigenous&per_page=20"
    )
    http = FakeHttp({base: json.dumps(page1), page1["next_page_url"]: json.dumps(page2)})
    source = FederalSource.model_validate(
        {
            "name": "Federal Register API",
            "method": "api",
            "content_type": "executive_order",
            "api_url_template": (
                "https://www.federalregister.gov/api/v1/documents.json"
                "?conditions[type]=PRESDOCU&conditions[term]={query}&per_page=20"
            ),
            "search_queries": ["missing indigenous"],
            "source_id": "fed-fr-eo-search",
            "review_needed": False,
            "max_pages": 5,
        }
    )
    candidates = list(ApiFetcher(http).discover(source))
    assert len(candidates) == 2
    assert "missing and murdered indigenous persons" in candidates[0].snippet.lower()
    assert "2021-09654" in candidates[1].url


def test_api_fetcher_paginates_doj_press_releases():
    from discovery.federal_schema import FederalSource

    page1 = {
        "metadata": {"responseInfo": {"status": 200}, "resultset": {"count": "40", "pagesize": "20", "page": 1}},
        "results": [
            {
                "title": "MMIP Awareness Day for Indigenous Communities",
                "url": "https://www.justice.gov/usao-ak/pr/mmip-page-1",
                "teaser": "Missing and murdered indigenous persons initiative",
            }
        ],
    }
    page2 = {
        "metadata": {"responseInfo": {"status": 200}, "resultset": {"count": "40", "pagesize": "20", "page": 2}},
        "results": [
            {
                "title": "Tribal MMIP Task Force update",
                "url": "https://www.justice.gov/usao-mt/pr/mmip-page-2",
                "teaser": "Missing indigenous persons coordination",
            }
        ],
    }
    base = (
        "https://www.justice.gov/api/v1/press_releases.json"
        "?parameters[title]=MMIP&pagesize=20&sort=date&direction=DESC"
    )
    page2_url = (
        "https://www.justice.gov/api/v1/press_releases.json"
        "?parameters[title]=MMIP&pagesize=20&sort=date&direction=DESC&page=2"
    )
    http = FakeHttp({base: json.dumps(page1), page2_url: json.dumps(page2)})
    source = FederalSource.model_validate(
        {
            "name": "DOJ News API",
            "method": "api",
            "content_type": "press_release",
            "api_url_template": (
                "https://www.justice.gov/api/v1/press_releases.json"
                "?parameters[title]={query}&pagesize=20&sort=date&direction=DESC"
            ),
            "search_queries": ["MMIP"],
            "source_id": "fed-doj-news",
            "review_needed": False,
            "max_pages": 5,
        }
    )
    candidates = list(ApiFetcher(http).discover(source))
    assert len(candidates) == 2
    assert candidates[0].url.endswith("/mmip-page-1")
    assert candidates[1].url.endswith("/mmip-page-2")


# --- Bug A: robots.txt must not be read with urllib's blocked default UA ------


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def test_robots_403_is_treated_as_unrestricted(monkeypatch):
    """A host that 403s robots.txt must not be blanket-blocked (NV, AR, VT)."""
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, (headers or {}).get("User-Agent", "")))
        return FakeResponse(403)

    monkeypatch.setattr("discovery.fetchers.requests.get", fake_get)
    http = HttpFetcher("UIC-PolicyTracker/1.0", per_domain_delay=0)
    assert http.can_fetch("https://gov.nv.gov/executive-orders/") is True
    # Tried the crawler UA first, then retried with a browser UA before giving up.
    assert len(calls) == 2
    assert calls[0][0] == "https://gov.nv.gov/robots.txt"
    assert "Mozilla/5.0" in calls[1][1]


def test_robots_404_is_treated_as_unrestricted(monkeypatch):
    monkeypatch.setattr(
        "discovery.fetchers.requests.get",
        lambda url, headers=None, timeout=None: FakeResponse(404),
    )
    http = HttpFetcher("UIC-PolicyTracker/1.0", per_domain_delay=0)
    assert http.can_fetch("https://example.gov/orders") is True


def test_robots_disallow_is_still_honored(monkeypatch):
    robots = "User-agent: *\nDisallow: /private/\n"
    monkeypatch.setattr(
        "discovery.fetchers.requests.get",
        lambda url, headers=None, timeout=None: FakeResponse(200, robots),
    )
    http = HttpFetcher("UIC-PolicyTracker/1.0", per_domain_delay=0)
    assert http.can_fetch("https://example.gov/private/secret") is False
    assert http.can_fetch("https://example.gov/proclamations/") is True


def test_robots_allow_all_permits_crawl(monkeypatch):
    """Nevada's real robots.txt."""
    monkeypatch.setattr(
        "discovery.fetchers.requests.get",
        lambda url, headers=None, timeout=None: FakeResponse(200, "User-agent: *\nAllow: /\n"),
    )
    http = HttpFetcher("UIC-PolicyTracker/1.0", per_domain_delay=0)
    assert http.can_fetch("https://gov.nv.gov/anything") is True


def test_robots_result_is_cached_per_domain(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse(200, "User-agent: *\nAllow: /\n")

    monkeypatch.setattr("discovery.fetchers.requests.get", fake_get)
    http = HttpFetcher("UIC-PolicyTracker/1.0", per_domain_delay=0)
    http.can_fetch("https://example.gov/a")
    http.can_fetch("https://example.gov/b")
    assert len(calls) == 1


# --- Bug B: row context for non-descriptive anchor text ----------------------


@pytest.mark.parametrize(
    "text",
    ["PDF", "2026-27", "21", "Read Proclamation", "View PDF", "Download",
     "https://evers.wi.gov/Documents/x.pdf", "Executive Order 2021-013"],
)
def test_weak_anchor_text(text):
    assert anchor_text_is_weak(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Missing and Murdered Indigenous Persons Awareness Day Proclamation",
        "Governor Establishes Task Force on Missing and Murdered Indigenous Women",
    ],
)
def test_descriptive_anchor_text_is_not_weak(text):
    assert anchor_text_is_weak(text) is False


# An MMIP program hub whose chrome is saturated with MMIP wording. Every link
# outside the document table has deliberately generic anchor text, so the only
# way any of them can pass prescreen is by borrowing context they should not get.
ROW_CONTEXT_HTML = """
<html><body>
  <nav class="navbar">
    <span>Missing and Murdered Indigenous Persons Program</span>
    <ul class="navbar-nav">
      <li><a href="/home">Home</a></li>
      <li><a href="/contact">Contact</a></li>
    </ul>
  </nav>
  <header id="masthead">
    <p>MMIP Task Force <a href="/about">About</a></p>
  </header>
  <aside class="sidebar">
    <p>Related: missing and murdered indigenous women resources
      <a href="/donate">Donate</a></p>
  </aside>
  <main>
    <table>
      <tr>
        <td>5/5/2026</td>
        <td>Proclamation: Missing and Murdered Indigenous Women and Girls Awareness Day</td>
        <td><a href="/docs/2026-mmiwg.pdf">PDF</a></td>
      </tr>
      <tr>
        <td>4/1/2026</td>
        <td>Proclamation: Small Business Week</td>
        <td><a href="/docs/2026-smallbiz.pdf">PDF</a></td>
      </tr>
    </table>
  </main>
  <footer>
    <p>MMIW hotline <a href="/hotline">Call</a></p>
  </footer>
</body></html>
"""


def test_row_context_admits_document_and_rejects_chrome():
    http = FakeHttp({"https://gov.example.gov/procs": ROW_CONTEXT_HTML})
    source = StateSource(
        state="EX", name="Example proclamations", method="index",
        url="https://gov.example.gov/procs", max_pages=1,
    )
    urls = [c.url for c in IndexFetcher(http).discover(source)]
    assert urls == ["https://gov.example.gov/docs/2026-mmiwg.pdf"]


def test_chrome_links_never_inherit_page_context():
    """The regression that made every nav link on an MMIP hub page a hit."""
    http = FakeHttp({"https://iad.example.gov/mmip/": ROW_CONTEXT_HTML})
    source = StateSource(
        state="EX", name="Example MMIP program hub", method="index",
        url="https://iad.example.gov/mmip/", max_pages=1,
    )
    urls = {c.url for c in IndexFetcher(http).discover(source)}
    for chrome_url in ("/home", "/contact", "/about", "/donate", "/hotline"):
        assert f"https://iad.example.gov{chrome_url}" not in urls
    assert urls == {"https://iad.example.gov/docs/2026-mmiwg.pdf"}


def test_oversized_container_is_not_used_as_context():
    """A whole page section must not lend its topic to every link inside it."""
    body = " ".join(f"Unrelated notice number {i}." for i in range(60))
    html = f"""
    <html><body><main><div class="listing">
      <p>Missing and Murdered Indigenous Persons Awareness Day was observed. {body}</p>
      <a href="/budget">Budget</a>
    </div></main></body></html>
    """
    http = FakeHttp({"https://gov.example.gov/x": html})
    source = StateSource(
        state="EX", name="Example", method="index",
        url="https://gov.example.gov/x", max_pages=1,
    )
    assert list(IndexFetcher(http).discover(source)) == []


def test_link_dense_container_is_not_used_as_context():
    html = """
    <html><body><main><div>
      <span>Missing and Murdered Indigenous Persons</span>
      <a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>
      <a href="/d">D</a><a href="/e">E</a><a href="/f">F</a>
    </div></main></body></html>
    """
    http = FakeHttp({"https://gov.example.gov/x": html})
    source = StateSource(
        state="EX", name="Example", method="index",
        url="https://gov.example.gov/x", max_pages=1,
    )
    assert list(IndexFetcher(http).discover(source)) == []


def test_descriptive_anchor_does_not_borrow_neighbour_topic():
    """A link with its own real title must be judged on that title alone."""
    html = """
    <html><body><main><li>
      Missing and Murdered Indigenous Women Awareness Day 2026 proclamation signed
      <a href="/news/annual-highway-construction-program-update">
        Annual Highway Construction Program Update Announcement
      </a>
    </li></main></body></html>
    """
    http = FakeHttp({"https://gov.example.gov/x": html})
    source = StateSource(
        state="EX", name="Example", method="index",
        url="https://gov.example.gov/x", max_pages=1,
    )
    assert list(IndexFetcher(http).discover(source)) == []


def test_aspnet_form_wrapper_does_not_block_context():
    """ASP.NET wraps whole pages in <form>; that must not count as chrome."""
    html = """
    <html><body><form id="aspnetForm"><table><tr>
      <td>26-09</td>
      <td>Proclamation on Missing and Murdered Indigenous Relatives</td>
      <td><a href="/docs/26-09.pdf">PDF</a></td>
    </tr></table></form></body></html>
    """
    http = FakeHttp({"https://www.lrl.example.gov/eo": html})
    source = StateSource(
        state="EX", name="Example", method="index",
        url="https://www.lrl.example.gov/eo", max_pages=1,
    )
    urls = [c.url for c in IndexFetcher(http).discover(source)]
    assert urls == ["https://www.lrl.example.gov/docs/26-09.pdf"]


# --- Pagination --------------------------------------------------------------


def test_current_page_number():
    assert current_page_number("https://x.gov/procs/") == 1
    assert current_page_number("https://x.gov/procs/page/4/") == 4
    assert current_page_number("https://x.gov/procs?page=3") == 3
    assert current_page_number("https://x.gov/procs?category=a&pageNum=7") == 7


def test_bump_page_url():
    assert bump_page_url("https://x.gov/procs?page=1", 2) == "https://x.gov/procs?page=2"
    assert bump_page_url("https://x.gov/procs/page/1/", 2) == "https://x.gov/procs/page/2/"
    assert bump_page_url("https://x.gov/procs", 2) == ""


def test_next_page_url_prefers_rel_next():
    html = '<html><body><a rel="next" href="/procs?page=2">Older</a></body></html>'
    assert next_page_url("https://x.gov/procs", html) == "https://x.gov/procs?page=2"


def test_next_page_url_falls_back_to_wordpress_convention():
    """gov.alaska.gov paginates only via JS; /page/N/ still resolves."""
    html = "<html><body><a href='/a'>A</a></body></html>"
    assert (
        next_page_url("https://gov.alaska.gov/proclamations/", html)
        == "https://gov.alaska.gov/proclamations/page/2/"
    )


def test_next_page_url_skips_file_paths():
    html = "<html><body><a href='/a'>A</a></body></html>"
    assert next_page_url("https://sos.gov/gov/execorders.aspx", html) == ""


def test_next_page_url_ignores_offsite_and_self_links():
    html = '<html><body><a rel="next" href="https://other.gov/procs">Next</a></body></html>'
    assert next_page_url("https://x.gov/procs", html) == "https://x.gov/procs/page/2/"


def test_index_fetcher_traverses_pages_up_to_max_pages():
    pages = {
        "https://gov.example.gov/procs": (
            '<html><body><li><a href="/p1">Item one filler text</a></li>'
            '<a rel="next" href="/procs?page=2">Next</a></body></html>'
        ),
        "https://gov.example.gov/procs?page=2": (
            "<html><body><li>Proclamation: Missing and Murdered Indigenous Persons Day"
            '<a href="/docs/mmip-2024.pdf">PDF</a></li>'
            '<a rel="next" href="/procs?page=3">Next</a></body></html>'
        ),
        "https://gov.example.gov/procs?page=3": (
            "<html><body><li>Proclamation: Arbor Day"
            '<a href="/docs/arbor.pdf">PDF</a></li></body></html>'
        ),
    }
    http = FakeHttp(pages)
    source = StateSource(
        state="EX", name="Example", method="index",
        url="https://gov.example.gov/procs", max_pages=3,
    )
    urls = [c.url for c in IndexFetcher(http).discover(source)]
    assert urls == ["https://gov.example.gov/docs/mmip-2024.pdf"]

    capped = StateSource(
        state="EX", name="Example", method="index",
        url="https://gov.example.gov/procs", max_pages=1,
    )
    assert list(IndexFetcher(FakeHttp(pages)).discover(capped)) == []


def test_index_fetcher_stops_when_pagination_repeats_content():
    """maine.gov re-serves page 1 for every ?page= value."""
    page = (
        "<html><body><li>Proclamation: Missing and Murdered Indigenous Persons"
        '<a href="/docs/mmip.pdf">PDF</a></li>'
        '<a rel="next" href="/procs?page=2">Next</a></body></html>'
    )

    class RepeatHttp(FakeHttp):
        def __init__(self):
            super().__init__({})
            self.fetched = []

        def fetch(self, url, method="GET", data=None, verify=True, ignore_robots=False,
                  user_agent=""):
            self.fetched.append(url)
            return page, "constant-hash", url

    http = RepeatHttp()
    source = StateSource(
        state="EX", name="Example", method="index",
        url="https://gov.example.gov/procs", max_pages=5,
    )
    list(IndexFetcher(http).discover(source))
    assert len(http.fetched) == 2


def test_index_fetcher_discards_repeat_page_reached_by_a_different_path():
    """governor.mt.gov answers /page/N/ with page 1, minting phantom duplicates."""
    listing = (
        "<html><body><main><li>May 5, 2026 - Missing and Murdered Indigenous "
        'Persons Awareness Day<a href="View?doc=mmip.pdf">May 5, 2026 - MMIP Day</a>'
        "</li></main><!--{nonce}--></body></html>"
    )
    pages = {
        "https://governor.mt.gov/Newsroom/Proclamations/": listing.format(nonce="a"),
        # Same items, different body bytes, so a content hash alone would not catch it.
        "https://governor.mt.gov/Newsroom/Proclamations/page/2/": listing.format(nonce="b"),
        "https://governor.mt.gov/Newsroom/Proclamations/page/3/": listing.format(nonce="c"),
    }
    source = StateSource(
        state="MT", name="MT proclamations", method="index",
        url="https://governor.mt.gov/Newsroom/Proclamations/", max_pages=3,
    )
    urls = [c.url for c in IndexFetcher(FakeHttp(pages)).discover(source)]
    assert urls == ["https://governor.mt.gov/Newsroom/Proclamations/View?doc=mmip.pdf"]


def test_index_fetcher_uses_page_url_template():
    pages = {
        "https://x.gov/procs": "<html><body><a href='/a'>Filler link text here</a></body></html>",
        "https://x.gov/procs?p=2": (
            "<html><body><li>Missing and Murdered Indigenous Relatives Day"
            '<a href="/docs/mmir.pdf">PDF</a></li></body></html>'
        ),
    }
    http = FakeHttp(pages)
    source = StateSource(
        state="EX", name="Example", method="index", url="https://x.gov/procs",
        max_pages=2, page_url_template="https://x.gov/procs?p={page}",
    )
    urls = [c.url for c in IndexFetcher(http).discover(source)]
    assert urls == ["https://x.gov/docs/mmir.pdf"]


# --- Cross-host documents ----------------------------------------------------


CROSS_HOST_HTML = """
<html><body><main><li>
  Proclamation: Missing and Murdered Indigenous Persons Awareness Day
  <a href="https://publications.tnsosfiles.com/procs/mmip.pdf">PDF</a>
  </li>
  <li>Proclamation: Missing and Murdered Indigenous Persons Awareness Day
  <a href="https://ads.example.com/tracker.pdf">PDF</a></li>
</main></body></html>
"""


def test_document_relative_hrefs_resolve_against_listing_path():
    """Montana links proclamations as 'View?doc=x.pdf'; origin-relative joins 404."""
    html = (
        "<html><body><main><li>May 5, 2026 - Missing and Murdered Indigenous "
        "Persons Awareness Day"
        "<a href=\"View?doc=260505MMIP.pdf\">May 5, 2026 - MMIP Awareness Day</a>"
        "</li></main></body></html>"
    )
    http = FakeHttp({"https://governor.mt.gov/Newsroom/Proclamations/": html})
    source = StateSource(
        state="MT", name="MT proclamations", method="index",
        url="https://governor.mt.gov/Newsroom/Proclamations/", max_pages=1,
    )
    urls = [c.url for c in IndexFetcher(http).discover(source)]
    assert urls == [
        "https://governor.mt.gov/Newsroom/Proclamations/View?doc=260505MMIP.pdf"
    ]


def test_document_relative_hrefs_resolve_after_cross_host_redirect():
    """Montana EO index redirects to gov.mt.gov; IndexFetcher must join against final URL."""
    html = (
        "<html><body><main><li>Executive Order 4-2026 Net Neutrality"
        '<a href="View?doc=EO42026NetNeutrality.pdf">Executive Order 4-2026</a>'
        "</li></main></body></html>"
    )
    captured: list[str] = []
    original_extract = HttpFetcher.extract_links

    def spy_extract(self, base_url, page_html, **kwargs):
        captured.append(base_url)
        return original_extract(self, base_url, page_html, **kwargs)

    class RedirectHttp(FakeHttp):
        def fetch(
            self,
            url: str,
            method: str = "GET",
            data=None,
            verify=True,
            ignore_robots=False,
            user_agent: str = "",
        ):
            if url == "https://governor.mt.gov/executive-orders":
                return (
                    html,
                    hashlib.sha256(html.encode()).hexdigest(),
                    "https://gov.mt.gov/Documents/GovernorsOffice/executiveorders/",
                )
            return super().fetch(url, method, data, verify, ignore_robots, user_agent)

    http = RedirectHttp({})
    source = StateSource(
        state="MT",
        name="MT executive orders",
        method="index",
        url="https://governor.mt.gov/executive-orders",
        content_type="executive_order",
        max_pages=1,
        allowed_extra_domains=["gov.mt.gov"],
    )
    HttpFetcher.extract_links = spy_extract
    try:
        list(IndexFetcher(http).discover(source))
    finally:
        HttpFetcher.extract_links = original_extract
    assert captured == ["https://gov.mt.gov/Documents/GovernorsOffice/executiveorders/"]
    urls = [
        link
        for link, _text, _ctx in original_extract(
            http,
            captured[0],
            html,
            allowed_extra_domains=["gov.mt.gov"],
        )
    ]
    assert urls == [
        "https://gov.mt.gov/Documents/GovernorsOffice/executiveorders/View?doc=EO42026NetNeutrality.pdf"
    ]


def test_root_relative_and_absolute_hrefs_still_resolve():
    html = (
        "<html><body><main>"
        "<li><a href='/docs/mmip.pdf'>Missing and Murdered Indigenous Persons Day 2026</a></li>"
        "<li><a href='https://gov.example.gov/abs/mmiw.pdf'>"
        "Missing and Murdered Indigenous Women Awareness Day 2026</a></li>"
        "</main></body></html>"
    )
    http = FakeHttp({"https://gov.example.gov/a/b/procs": html})
    source = StateSource(
        state="EX", name="Example", method="index",
        url="https://gov.example.gov/a/b/procs", max_pages=1,
    )
    urls = sorted(c.url for c in IndexFetcher(http).discover(source))
    assert urls == [
        "https://gov.example.gov/abs/mmiw.pdf",
        "https://gov.example.gov/docs/mmip.pdf",
    ]


def test_off_domain_documents_require_allowlist():
    http = FakeHttp({"https://tnsos.net/procs": CROSS_HOST_HTML})
    source = StateSource(
        state="TN", name="TN procs", method="index",
        url="https://tnsos.net/procs", max_pages=1,
    )
    assert list(IndexFetcher(http).discover(source)) == []


def test_allowed_extra_domains_admits_document_host_only():
    http = FakeHttp({"https://tnsos.net/procs": CROSS_HOST_HTML})
    source = StateSource(
        state="TN", name="TN procs", method="index",
        url="https://tnsos.net/procs", max_pages=1,
        allowed_extra_domains=["publications.tnsosfiles.com"],
    )
    urls = [c.url for c in IndexFetcher(http).discover(source)]
    assert urls == ["https://publications.tnsosfiles.com/procs/mmip.pdf"]


# --- Opaque PDF / weak EO anchor: fetch document text before prescreen ----------


def test_index_fetcher_fetches_opaque_pdf_for_eo_prescreen():
    """NM-style EO listing: anchor 'Executive Order 2021-013' needs PDF body."""
    html = """
    <html><body><main><ul>
      <li><a href="/assets/eo-2021-013.pdf">Executive Order 2021-013</a></li>
      <li><a href="/assets/eo-budget.pdf">Executive Order 2026-001</a></li>
    </ul></main></body></html>
    """
    mmip_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 55>>stream\n"
        b"BT /F1 12 Tf 100 700 Td (Missing and Murdered Indigenous Women Task Force) Tj ET\n"
        b"endstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )

    class DocHttp(FakeHttp):
        def fetch_content(self, url, verify=True, ignore_robots=False, user_agent=""):
            if url.endswith("eo-2021-013.pdf"):
                return mmip_pdf, "pdfhash", "application/pdf"
            if url.endswith("eo-budget.pdf"):
                return b"budget pdf", "bh", "application/pdf"
            return b"", "", ""

        def fetch(self, url, method="GET", data=None, verify=True, ignore_robots=False,
                  user_agent=""):
            return super().fetch(url, method, data, verify, ignore_robots, user_agent)

    http = DocHttp({"https://gov.example.gov/executive-orders/": html})
    source = StateSource(
        state="EX", name="Example EOs", method="index",
        url="https://gov.example.gov/executive-orders/",
        content_type="executive_order", max_pages=1,
    )
    # Patch PDF extraction — minimal hand-built PDF above may not parse in pypdf.
    from discovery import fetchers as fetchers_mod

    real_extract = fetchers_mod.extract_document_text

    def fake_extract(content, url, content_type=""):
        if "eo-2021-013" in url:
            return "Executive Order establishing Missing and Murdered Indigenous Women Task Force"
        if "eo-budget" in url:
            return "Annual state budget allocation"
        return real_extract(content, url, content_type)

    fetchers_mod.extract_document_text = fake_extract
    try:
        urls = [c.url for c in IndexFetcher(http).discover(source)]
    finally:
        fetchers_mod.extract_document_text = real_extract
    assert urls == ["https://gov.example.gov/assets/eo-2021-013.pdf"]


def test_index_fetcher_does_not_fetch_documents_for_press_release_sources():
    html = """
    <html><body><a href="/docs/report.pdf">PDF</a></body></html>
    """
    fetched = []

    class SpyHttp(FakeHttp):
        def fetch_content(self, url, verify=True, ignore_robots=False, user_agent=""):
            fetched.append(url)
            return b"Missing and murdered indigenous persons report", "h", "application/pdf"

    http = SpyHttp({"https://gov.example.gov/news": html})
    source = StateSource(
        state="EX", name="News", method="index",
        url="https://gov.example.gov/news", content_type="press_release", max_pages=1,
    )
    assert list(IndexFetcher(http).discover(source)) == []
    assert fetched == []


def test_extract_table_document_links_builds_pa_eo_pdfs():
    html = """
    <html><body><table>
    <tr><th>Number</th><th>Title</th></tr>
    <tr><td></td><td>2024-01</td><td>Climate Action</td><td>1/2/2024</td></tr>
    <tr><td>*</td><td>2025-01</td><td>Filling Critical Vacancies</td><td>3/5/2025</td></tr>
    <tr><td></td><td>MD 105.01</td><td>Allocation of Funds</td></tr>
    </table></body></html>
    """
    template = "https://www.pa.gov/content/dam/copapwp-pagov/en/oa/documents/policies/eo/{number}.pdf"
    links = extract_table_document_links(html, template)
    urls = [url for url, _text, _ctx in links]
    assert urls == [
        "https://www.pa.gov/content/dam/copapwp-pagov/en/oa/documents/policies/eo/2025-01.pdf",
        "https://www.pa.gov/content/dam/copapwp-pagov/en/oa/documents/policies/eo/2024-01.pdf",
    ]
    assert "Executive Order 2025-01" in links[0][1]
    assert "Filling Critical Vacancies" in links[0][2]


def test_index_fetcher_uses_document_url_template():
    html = """
    <html><body><table>
    <tr><td></td><td>2024-01</td><td>Climate Action</td></tr>
    </table></body></html>
    """
    pdf_url = "https://www.pa.gov/content/dam/copapwp-pagov/en/oa/documents/policies/eo/2024-01.pdf"
    index_url = "https://www.pacodeandbulletin.gov/secure/pacode/data/004/chapter1/s1.4.html"

    class DocHttp(FakeHttp):
        def fetch_content(self, url, verify=True, ignore_robots=False, user_agent=""):
            if url == pdf_url:
                return b"%PDF-1.4", "pdfhash", "application/pdf"
            return b"", "", ""

    http = DocHttp({index_url: html})
    source = StateSource(
        state="PA",
        name="PA pacode EO",
        method="index",
        url=index_url,
        content_type="executive_order",
        document_url_template=pdf_url.replace("2024-01", "{number}"),
        max_pages=1,
    )
    from discovery import fetchers as fetchers_mod

    real_extract = fetchers_mod.extract_document_text
    fetchers_mod.extract_document_text = lambda _content, url, _ct="": (
        "Executive Order on Missing and Murdered Indigenous Persons" if "2024-01" in url else ""
    )
    try:
        urls = [c.url for c in IndexFetcher(http).discover(source)]
    finally:
        fetchers_mod.extract_document_text = real_extract
    assert urls == [pdf_url]
