"""HTTP fetch helpers and source-type fetchers for state site discovery."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from typing import Iterator
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from discovery.browser_fetcher import looks_like_bot_wall
from discovery.models import Candidate, utc_now_iso
from discovery.queries import keyword_prescreen
from discovery.federal_schema import (
    federal_register_document_id,
    is_doj_press_api,
    is_federal_register_api,
    is_federal_register_document_url,
)
from discovery.source_schema import DEFAULT_SEARCH_QUERIES, StateSource
from discovery.url_utils import normalize_url

if False:  # TYPE_CHECKING
    from discovery.browser_fetcher import BrowserRenderer

logger = logging.getLogger(__name__)

# Browser-like UA for sites that 403 the default crawler string (justice.gov, etc.).
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# --- Row-context extraction -------------------------------------------------
# Most EO/proclamation archives link documents with useless anchor text ("PDF",
# "2026-27", "21", "Read Proclamation") and carry the real title in the enclosing
# list item, table row, or card. Pulling that in is the only way those documents
# can ever pass prescreen — but it must stay tightly bounded, because feeding
# whole-page text to the prescreen previously made every nav link on an MMIP hub
# page a false positive.

# Containers that hold one logical record. Ordered smallest-scope first.
ROW_CONTEXT_TAGS = ("li", "tr", "dd", "td", "figcaption", "article", "p", "div", "section")
# Ancestors that mean the link is site chrome, never a document row. <form> is
# deliberately absent: ASP.NET WebForms wraps whole pages in one, so treating it
# as chrome would blank the context on most Secretary of State archives.
CHROME_TAGS = frozenset({"nav", "header", "footer", "aside"})
CHROME_ATTR_RE = re.compile(
    r"(?:^|[-_ ])(?:nav|navigation|navbar|menu|megamenu|breadcrumbs?|pager|pagination|"
    r"sidebar|social|share|skip|footer|header|banner|cookie|toolbar|utility|masthead)"
    r"(?:[-_ ]|$)",
    re.IGNORECASE,
)
# A record row is short and links to few things; anything larger is a page
# section whose text would smear one document's title across its neighbours.
MAX_ROW_CONTEXT_CHARS = 400
MAX_ROW_CONTEXT_LINKS = 4
ROW_CONTEXT_CLIMB_LIMIT = 6
# Anchor text with at least this many letters is treated as a real title and
# prescreened on its own, so a descriptive link never inherits a sibling's topic.
DESCRIPTIVE_ANCHOR_LETTERS = 40
# EO/proclamation indexes often link PDFs with anchor text like "Executive Order 2021-013"
# that carries no MMIP signal; prescreen must read the document body.
DOC_URL_RE = re.compile(
    r"\.pdf(?:$|[?#])|/assets/|view\?doc=|executive[- ]order|/eo[-/]|/documents/",
    re.IGNORECASE,
)
MAX_DOCUMENT_TEXT_CHARS = 8000
MAX_DOCUMENT_PDF_PAGES = 2

TABLE_EO_NUMBER_RE = re.compile(r"^\d{4}-\d{2}$")

FILLER_ANCHOR_RE = re.compile(
    r"^(?:pdf|html?|docx?|rtf|txt|link|here|more|details?|full text|open|view|download|"
    r"read|read more|read the \w+|click here|continue reading|learn more|see more|"
    r"view (?:pdf|document|order|proclamation)|download (?:pdf|document)|"
    r"read (?:pdf|document|order|proclamation))$",
    re.IGNORECASE,
)


def _letter_count(text: str) -> int:
    return sum(1 for char in text if char.isalpha())


def anchor_text_is_weak(text: str) -> bool:
    """True when anchor text cannot plausibly carry a document title.

    Covers filler ("PDF", "Read Proclamation"), bare numbers/dates ("21",
    "2026-27"), raw URLs, and anything too short to be a title.
    """
    stripped = (text or "").strip()
    if not stripped:
        return True
    if _is_url_context(stripped):
        return True
    if FILLER_ANCHOR_RE.match(stripped):
        return True
    return _letter_count(stripped) < DESCRIPTIVE_ANCHOR_LETTERS


def _in_chrome(anchor) -> bool:
    for ancestor in anchor.parents:
        name = getattr(ancestor, "name", "") or ""
        if name in CHROME_TAGS:
            return True
        if name in ("body", "html", "[document]"):
            break
        attrs = ancestor.attrs if hasattr(ancestor, "attrs") else {}
        blob = " ".join(
            [" ".join(attrs.get("class") or []), str(attrs.get("id") or ""), str(attrs.get("role") or "")]
        )
        if blob.strip() and CHROME_ATTR_RE.search(blob):
            return True
    return False


def row_context(anchor) -> str:
    """Text of the smallest record-shaped ancestor holding this anchor.

    Returns "" for chrome links and for containers too large or too link-dense
    to represent a single document.
    """
    if _in_chrome(anchor):
        return ""
    best = ""
    for depth, ancestor in enumerate(anchor.parents):
        if depth >= ROW_CONTEXT_CLIMB_LIMIT:
            break
        name = getattr(ancestor, "name", "") or ""
        if name in ("body", "html", "[document]"):
            break
        if name not in ROW_CONTEXT_TAGS:
            continue
        text = ancestor.get_text(" ", strip=True)
        if not text or len(text) > MAX_ROW_CONTEXT_CHARS:
            break
        if len(ancestor.find_all("a", href=True)) > MAX_ROW_CONTEXT_LINKS:
            break
        best = text
    return best


class HttpFetcher:
    """Shared HTTP client with robots.txt and rate limiting."""

    def __init__(self, user_agent: str, per_domain_delay: float = 2.0):
        self.user_agent = user_agent
        self.per_domain_delay = per_domain_delay
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self._last_fetch: dict[str, float] = {}

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def _load_robots(self, url: str, user_agent: str) -> RobotFileParser | None:
        """Fetch and parse robots.txt, or return None meaning "no restrictions".

        ``RobotFileParser.read()`` uses urllib's default User-Agent, which many
        state portals answer with 403; the parser then sets ``disallow_all`` and
        silently blocks the whole host even though its real robots.txt permits
        crawling. Fetch it ourselves and retry with a browser UA before giving up.
        """
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        body = ""
        for agent in (user_agent or self.user_agent, BROWSER_UA):
            try:
                response = requests.get(robots_url, headers={"User-Agent": agent}, timeout=15)
            except Exception as exc:
                logger.debug("robots.txt fetch failed for %s: %s", robots_url, exc)
                return None
            if response.status_code == 200:
                body = response.text
                break
            logger.debug(
                "robots.txt %s returned %s for UA %r", robots_url, response.status_code, agent[:24]
            )
        else:
            # Unreadable robots.txt (403/404/5xx) means we learned nothing about
            # the site's policy, not that everything is forbidden.
            return None
        rp = RobotFileParser()
        rp.parse(body.splitlines())
        return rp

    def can_fetch(self, url: str, user_agent: str = "") -> bool:
        domain = self._domain(url)
        if domain not in self._robots_cache:
            self._robots_cache[domain] = self._load_robots(url, user_agent)
        rp = self._robots_cache[domain]
        if rp is None:
            return True
        return rp.can_fetch(user_agent or self.user_agent, url)

    def _rate_limit(self, domain: str) -> None:
        last = self._last_fetch.get(domain, 0)
        elapsed = time.time() - last
        if elapsed < self.per_domain_delay:
            time.sleep(self.per_domain_delay - elapsed)
        self._last_fetch[domain] = time.time()

    def fetch(
        self,
        url: str,
        method: str = "GET",
        data: dict | None = None,
        verify: bool | None = None,
        ignore_robots: bool = False,
        user_agent: str = "",
    ) -> tuple[str, str, str]:
        domain = self._domain(url)
        skip_robots = ignore_robots or os.getenv("CRAWLER_IGNORE_ROBOTS", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        if not skip_robots and not self.can_fetch(url, user_agent):
            logger.info("Robots.txt disallows fetch: %s", url)
            return "", "", ""
        self._rate_limit(domain)
        headers = {"User-Agent": user_agent or self.user_agent}
        ssl_verify = verify if verify is not None else True
        try:
            if method.upper() == "POST":
                response = requests.post(
                    url, headers=headers, data=data or {}, timeout=30, verify=ssl_verify
                )
            else:
                response = requests.get(url, headers=headers, timeout=30, verify=ssl_verify)
            response.raise_for_status()
            content = response.text
            if looks_like_bot_wall(content):
                logger.warning(
                    "HTTP bot wall for %s (status=%s len=%s)",
                    url,
                    response.status_code,
                    len(content),
                )
                return "", "", ""
            content_hash = hashlib.sha256(response.content).hexdigest()
            return content, content_hash, response.url
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return "", "", ""

    def fetch_content(
        self,
        url: str,
        verify: bool | None = None,
        ignore_robots: bool = False,
        user_agent: str = "",
    ) -> tuple[bytes, str, str]:
        """Fetch raw response bytes for document text extraction."""
        domain = self._domain(url)
        skip_robots = ignore_robots or os.getenv("CRAWLER_IGNORE_ROBOTS", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        if not skip_robots and not self.can_fetch(url, user_agent):
            logger.info("Robots.txt disallows fetch: %s", url)
            return b"", "", ""
        self._rate_limit(domain)
        headers = {"User-Agent": user_agent or self.user_agent}
        ssl_verify = verify if verify is not None else True
        try:
            response = requests.get(url, headers=headers, timeout=30, verify=ssl_verify)
            response.raise_for_status()
            content = response.content
            if looks_like_bot_wall(content.decode("utf-8", errors="replace")):
                logger.warning(
                    "HTTP bot wall for %s (status=%s len=%s)",
                    url,
                    response.status_code,
                    len(content),
                )
                return b"", "", ""
            content_hash = hashlib.sha256(content).hexdigest()
            content_type = response.headers.get("Content-Type", "")
            return content, content_hash, content_type
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return b"", "", ""

    def extract_links(
        self,
        base_url: str,
        html: str,
        same_domain_only: bool = True,
        link_selector: str | None = None,
        link_context_parent: str | None = None,
        allowed_extra_domains: list[str] | None = None,
    ) -> list[tuple[str, str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        base_domain = self._domain(base_url)
        allowed_domains = {base_domain} | {
            d.strip().lower().lstrip(".") for d in (allowed_extra_domains or []) if d.strip()
        }
        links: list[tuple[str, str, str]] = []
        if link_selector:
            anchors = soup.select(link_selector)
        else:
            anchors = soup.find_all("a", href=True)
        for anchor in anchors:
            href = anchor.get("href", "").strip()
            if (
                not href
                or href.startswith("#")
                or href.startswith("mailto:")
                or href.lower().startswith("javascript:")
                or href.lower().startswith("data:")
            ):
                continue
            # Resolve against the full listing URL, not just its origin: Montana's
            # proclamation archive uses document-relative hrefs ("View?doc=x.pdf")
            # that only resolve correctly relative to /Newsroom/Proclamations/.
            absolute = urljoin(base_url, href)
            abs_scheme = urlparse(absolute).scheme.lower()
            if abs_scheme not in ("http", "https"):
                continue
            if same_domain_only and not self._domain_allowed(absolute, allowed_domains):
                continue
            text = anchor.get_text(" ", strip=True)
            if not text:
                continue
            context = ""
            if link_context_parent:
                parent = anchor.find_parent(link_context_parent)
                if parent is not None:
                    context = parent.get_text(" ", strip=True)
            elif anchor_text_is_weak(text):
                context = row_context(anchor)
            links.append((absolute, text, context))
        return links

    @staticmethod
    def _domain_allowed(url: str, allowed_domains: set[str]) -> bool:
        domain = urlparse(url).netloc.lower()
        return any(domain == allowed or domain.endswith("." + allowed) for allowed in allowed_domains)


def extract_table_document_links(
    html: str,
    document_url_template: str,
) -> list[tuple[str, str, str]]:
    """Build document links from table rows when an index has no hrefs.

    PA pacode lists executive orders in an HTML table with issuance numbers
    (YYYY-NN) but no links; PDFs live on pa.gov at a predictable path.
    """
    if not html or not document_url_template or "{number}" not in document_url_template:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        number = ""
        title = ""
        for idx, cell in enumerate(cells):
            cleaned = cell.replace("*", "").strip()
            if TABLE_EO_NUMBER_RE.match(cleaned):
                number = cleaned
                for later in cells[idx + 1 :]:
                    if later.strip():
                        title = later.strip()
                        break
                break
        if not number:
            continue
        url = document_url_template.replace("{number}", number)
        if url in seen:
            continue
        seen.add(url)
        link_text = f"Executive Order {number}"
        context = f"{link_text} {title}".strip() if title else link_text
        links.append((url, link_text, context))
    # Newest issuances first: PA only hosts recent PDFs; probing oldest rows
    # wastes the per-run document fetch cap on predictable 404s.
    links.sort(key=lambda item: item[0], reverse=True)
    return links


def _fetch_html(
    http: HttpFetcher,
    browser: "BrowserRenderer | None",
    source: StateSource,
    url: str,
    method: str = "GET",
    query: str | None = None,
) -> tuple[str, str, str]:
    if source.render_js and browser is not None:
        wait = source.browser_wait_selector or None
        if query and source.browser_input_selector and source.browser_submit_selector:
            html, content_hash = browser.fetch_search(
                url,
                query,
                input_selector=source.browser_input_selector,
                submit_selector=source.browser_submit_selector,
                click_selector=source.browser_click_selector or None,
                wait_selector=wait,
                ignore_https=not source.ssl_verify,
                user_agent=source.user_agent or None,
            )
        else:
            html, content_hash = browser.fetch(
                url,
                wait_selector=wait,
                ignore_https=not source.ssl_verify,
                user_agent=source.user_agent or None,
            )
        return html, content_hash, url
    return http.fetch(
        url,
        method=method,
        verify=source.ssl_verify,
        ignore_robots=source.ignore_robots,
        user_agent=source.user_agent,
    )


def _is_url_context(context: str) -> bool:
    lowered = context.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _pdf_text(content: bytes, max_pages: int = MAX_DOCUMENT_PDF_PAGES) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        parts: list[str] = []
        for page in reader.pages[:max_pages]:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n".join(parts)[:MAX_DOCUMENT_TEXT_CHARS]
    except Exception as exc:
        logger.debug("PDF text extraction failed: %s", exc)
        return ""


def _html_text(content: bytes) -> str:
    html = content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)[:MAX_DOCUMENT_TEXT_CHARS]


def extract_document_text(content: bytes, url: str, content_type: str = "") -> str:
    if not content:
        return ""
    lowered_url = (url or "").lower()
    ct = (content_type or "").lower()
    if content[:5] == b"%PDF-" or "pdf" in ct or lowered_url.endswith(".pdf") or ".pdf?" in lowered_url:
        return _pdf_text(content)
    return _html_text(content)


def _strip_html_text(value: str) -> str:
    if not value or "<" not in value:
        return (value or "").strip()
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def federal_register_item_snippet(item: dict) -> str:
    """Best-available snippet from a Federal Register search API result."""
    excerpts = item.get("excerpts")
    if excerpts:
        text = _strip_html_text(str(excerpts))
        if text:
            return text[:500]
    for key in ("abstract", "description"):
        val = item.get(key)
        if val:
            return str(val).strip()[:500]
    return ""


def fetch_federal_register_document_text(http: HttpFetcher, url: str) -> tuple[str, str]:
    """Fetch presidential document text via the Federal Register developer API."""
    doc_id = federal_register_document_id(url)
    if not doc_id:
        return "", ""
    meta_url = f"https://www.federalregister.gov/api/v1/documents/{doc_id}.json"
    meta_body, content_hash, _ = http.fetch(meta_url, ignore_robots=True)
    if not meta_body:
        return "", ""
    try:
        detail = json.loads(meta_body)
    except json.JSONDecodeError:
        return "", content_hash

    parts: list[str] = []
    abstract = str(detail.get("abstract") or "").strip()
    if abstract:
        parts.append(abstract)

    raw_text_url = str(detail.get("raw_text_url") or "")
    if raw_text_url:
        raw_body, raw_hash, content_type = http.fetch_content(raw_text_url, ignore_robots=True)
        if raw_body:
            content_hash = raw_hash or content_hash
            raw_text = extract_document_text(raw_body, raw_text_url, content_type)
            if raw_text:
                parts.append(raw_text)

    if not parts:
        xml_url = str(detail.get("full_text_xml_url") or "")
        if xml_url:
            xml_body, xml_hash, _ = http.fetch_content(xml_url, ignore_robots=True)
            if xml_body:
                content_hash = xml_hash or content_hash
                xml_text = _strip_html_text(xml_body.decode("utf-8", errors="replace"))
                if xml_text:
                    parts.append(xml_text)

    combined = "\n\n".join(part for part in parts if part).strip()
    return combined[:MAX_DOCUMENT_TEXT_CHARS], content_hash


def is_justice_gov_url(url: str) -> bool:
    return "justice.gov" in (url or "").lower()


def is_mass_gov_url(url: str) -> bool:
    return "mass.gov" in (url or "").lower()


def is_browser_gated_url(url: str) -> bool:
    """Hosts that 403 plain HTTP and need Playwright for document pages."""
    return is_justice_gov_url(url) or is_mass_gov_url(url)


def fetch_justice_gov_content(
    http: HttpFetcher,
    url: str,
    browser: BrowserRenderer | None = None,
    user_agent: str = "",
) -> tuple[bytes, str, str]:
    """Fetch bot-gated HTML (justice.gov, mass.gov) via HTTP then Playwright."""
    ua = user_agent or BROWSER_UA
    body, content_hash, content_type = http.fetch_content(
        url,
        ignore_robots=True,
        user_agent=ua,
    )
    needs_browser = False
    if not body:
        needs_browser = True
    else:
        html = body.decode("utf-8", errors="replace")
        if looks_like_bot_wall(html):
            needs_browser = True
        elif not extract_document_text(body, url, content_type).strip():
            needs_browser = True

    if not needs_browser:
        return body, content_hash, content_type

    if browser is not None:
        html, browser_hash = browser.fetch(url, user_agent=ua, settle_ms=2500)
    else:
        html, browser_hash = _fetch_justice_gov_via_browser(url, ua)
    if html:
        return html.encode("utf-8", errors="replace"), browser_hash or content_hash, "text/html"
    return b"", content_hash, content_type


def _fetch_justice_gov_via_browser(
    url: str,
    user_agent: str,
) -> tuple[str, str]:
    """Run Playwright in a worker thread (safe after httpx/async LLM calls)."""
    import concurrent.futures

    def _run() -> tuple[str, str]:
        from discovery.browser_fetcher import BrowserRenderer

        owned = BrowserRenderer(user_agent)
        try:
            return owned.fetch(url, user_agent=user_agent, settle_ms=2500)
        finally:
            owned.stop()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run).result()


EO_PROC_TITLE_RE = re.compile(
    r"\b(?:executive\s+order|proclamation|administrative\s+order|declaration|emergency\s+proclamation)\b",
    re.IGNORECASE,
)


def _should_fetch_document_text(source: StateSource, link_url: str, link_text: str) -> bool:
    if source.content_type not in ("executive_order", "proclamation"):
        return False
    titleish = bool(EO_PROC_TITLE_RE.search(link_text or ""))
    is_pdfish = bool(DOC_URL_RE.search(link_url) or link_url.lower().endswith(".pdf"))
    if anchor_text_is_weak(link_text):
        return is_pdfish or titleish
    return titleish


def _snippet_from_link(
    link_text: str,
    context: str = "",
    search_query: str = "",
) -> str:
    """Build snippet from link text + real context.

    search_query may be noted for traceability after a candidate already passed
    prescreen on link/context alone — it must never be the sole MMIP signal.
    """
    if context and context != link_text and not _is_url_context(context):
        base = f"{link_text}\n{context}".strip()
    else:
        base = link_text
    if search_query and search_query.lower() not in base.lower():
        return f"{base}\n(search: {search_query})".strip()
    return base


def _candidate_from_link(
    source: StateSource,
    link_url: str,
    link_text: str,
    content_hash: str = "",
    context: str = "",
    search_query: str = "",
    http: HttpFetcher | None = None,
    doc_fetch_count: list[int] | None = None,
) -> Candidate | None:
    # Prescreen on link text + real surrounding context only.
    # Never use source.name / listing URL / search_query — those often contain
    # "MMIP" and previously admitted every nav chrome link on MMIP hub pages.
    if context and not _is_url_context(context):
        prescreen_text = f"{link_text}\n{context}".strip()
    else:
        prescreen_text = link_text
    doc_context = ""
    if not keyword_prescreen(prescreen_text):
        if http and _should_fetch_document_text(source, link_url, link_text):
            max_fetches = int(getattr(source, "max_document_fetches", 0) or 0)
            if max_fetches and doc_fetch_count is not None and doc_fetch_count[0] >= max_fetches:
                return None
            ua = source.user_agent or BROWSER_UA
            if source.render_js or is_browser_gated_url(link_url):
                body, doc_hash, content_type = fetch_justice_gov_content(
                    http,
                    link_url,
                    user_agent=ua,
                )
            else:
                body, doc_hash, content_type = http.fetch_content(
                    link_url,
                    verify=source.ssl_verify,
                    ignore_robots=source.ignore_robots,
                    user_agent=ua,
                )
            if not body:
                return None
            if max_fetches and doc_fetch_count is not None:
                doc_fetch_count[0] += 1
            doc_text = extract_document_text(body, link_url, content_type)
            if doc_text and keyword_prescreen(doc_text):
                doc_context = doc_text[:500]
                if doc_hash:
                    content_hash = doc_hash
            else:
                return None
        else:
            return None
    snippet_context = doc_context or context
    return Candidate(
        source="state_site",
        state=source.state,
        url=link_url,
        title=link_text,
        snippet=_snippet_from_link(link_text, snippet_context, search_query),
        content_hash=content_hash,
        discovered_at=utc_now_iso(),
    )


def _title_from_sample_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    slug = slug.replace(".html", "").replace(".htm", "").replace(".pdf", "")
    return slug.replace("-", " ").replace("_", " ").strip() or url


def _candidates_from_sample_urls(source: StateSource) -> Iterator[Candidate]:
    """Yield known MMIP deep links / hub pages stored on the source config."""
    for sample_url in source.sample_urls or []:
        url = (sample_url or "").strip()
        if not url.startswith("http"):
            continue
        title = _title_from_sample_url(url)
        candidate = _candidate_from_link(
            source,
            url,
            title,
            context=f"{source.name}\nknown MMIP page",
        )
        if candidate:
            yield candidate


YEAR_SLUG_PLACEHOLDER = "{year}"


def year_slug_probe_range(*, back_years: int = 7) -> range:
    """Inclusive calendar years to probe, newest first (current year .. current-back)."""
    current = date.today().year
    return range(current, current - back_years - 1, -1)


def _candidates_from_year_slug_templates(
    source: StateSource,
    http: HttpFetcher,
) -> Iterator[Candidate]:
    """Cheap HEAD/GET probes for MMIP awareness-day slugs missing from index pages."""
    templates = [t.strip() for t in (source.year_slug_templates or []) if t.strip()]
    if not templates or source.content_type != "proclamation":
        return
    seen: set[str] = set()
    for template in templates:
        if YEAR_SLUG_PLACEHOLDER not in template:
            continue
        for year in year_slug_probe_range():
            url = template.replace(YEAR_SLUG_PLACEHOLDER, str(year))
            norm = normalize_url(url)
            if norm in seen:
                continue
            seen.add(norm)
            html, content_hash, final_url = http.fetch(
                url,
                verify=source.ssl_verify,
                ignore_robots=source.ignore_robots,
                user_agent=source.user_agent,
            )
            if not html:
                continue
            probe_url = final_url or url
            title = _title_from_sample_url(probe_url)
            candidate = _candidate_from_link(
                source,
                probe_url,
                title,
                content_hash=content_hash,
                context=f"{source.name}\nyear-slug probe {year}",
            )
            if candidate:
                yield candidate


NEXT_LINK_TEXT_RE = re.compile(
    r"^(?:next(?:\s+(?:page|posts?|results?|»|›|>))?|older(?:\s+posts?)?|»|›|→|>>|>)$",
    re.IGNORECASE,
)
NEXT_CLASS_RE = re.compile(r"(?:^|[-_ ])(?:next|pagination-next|pager-next)(?:[-_ ]|$)", re.I)
PAGE_QUERY_KEYS = ("page", "pageno", "pagenum", "pagenumber", "pg", "p")
PAGE_PATH_RE = re.compile(r"(/page/)(\d+)(/?)$", re.IGNORECASE)


def current_page_number(url: str) -> int:
    parsed = urlparse(url)
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in PAGE_QUERY_KEYS and value.isdigit():
            return max(1, int(value))
    match = PAGE_PATH_RE.search(parsed.path)
    if match:
        return max(1, int(match.group(2)))
    return 1


def bump_page_url(url: str, page: int) -> str:
    """Rewrite an existing page indicator in the URL, or return "" if absent."""
    parsed = urlparse(url)
    params = parse_qsl(parsed.query, keep_blank_values=True)
    for idx, (key, _value) in enumerate(params):
        if key.lower() in PAGE_QUERY_KEYS:
            params[idx] = (key, str(page))
            return urlunparse(parsed._replace(query=urlencode(params)))
    if PAGE_PATH_RE.search(parsed.path):
        new_path = PAGE_PATH_RE.sub(rf"\g<1>{page}\g<3>", parsed.path)
        return urlunparse(parsed._replace(path=new_path))
    return ""


def next_page_url(current_url: str, html: str, next_page_selector: str = "") -> str:
    """Best-effort next-page URL from a listing page, or "" when there is none."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []

    def add(node) -> None:
        if node is None:
            return
        href = (node.get("href") or "").strip()
        if href and not href.startswith("#") and not href.lower().startswith("javascript:"):
            candidates.append(urljoin(current_url, href))

    if next_page_selector:
        add(soup.select_one(next_page_selector))
    for node in soup.find_all(["a", "link"], rel=True):
        rels = node.get("rel") or []
        if any(str(rel).lower() == "next" for rel in rels):
            add(node)
    for node in soup.find_all("a", href=True):
        attrs = node.attrs
        blob = " ".join([" ".join(attrs.get("class") or []), str(attrs.get("id") or "")])
        label = (attrs.get("aria-label") or attrs.get("title") or "").strip()
        text = node.get_text(" ", strip=True)
        if (blob and NEXT_CLASS_RE.search(blob)) or NEXT_LINK_TEXT_RE.match(text) or (
            label and NEXT_LINK_TEXT_RE.match(label)
        ):
            add(node)

    wanted_page = current_page_number(current_url) + 1
    for node in soup.find_all("a", href=True):
        if node.get_text(" ", strip=True) == str(wanted_page):
            add(node)

    current_host = urlparse(current_url).netloc.lower()
    current_norm = normalize_url(current_url)
    for candidate in candidates:
        if urlparse(candidate).netloc.lower() != current_host:
            continue
        if normalize_url(candidate) == current_norm:
            continue
        return candidate

    guessed = bump_page_url(current_url, wanted_page)
    if guessed and normalize_url(guessed) != current_norm:
        return guessed
    return _guess_wordpress_page(current_url, wanted_page)


def _guess_wordpress_page(current_url: str, page: int) -> str:
    """Fall back to the /page/N/ convention for extensionless listing paths.

    Several WordPress archives (gov.alaska.gov/proclamations/ among them) paginate
    only through a JS control, so no next-page anchor exists in the served HTML —
    but /page/2/ resolves. A miss returns 404 or repeats page 1, both of which the
    caller already stops on.
    """
    parsed = urlparse(current_url)
    path = parsed.path
    if PAGE_PATH_RE.search(path) or parsed.query:
        return ""
    last_segment = path.rstrip("/").rsplit("/", 1)[-1]
    if "." in last_segment or not last_segment:
        return ""
    return urlunparse(parsed._replace(path=f"{path.rstrip('/')}/page/{page}/"))


class IndexFetcher:
    def __init__(self, http: HttpFetcher, browser: "BrowserRenderer | None" = None):
        self.http = http
        self.browser = browser

    def _iter_pages(self, source: StateSource) -> Iterator[tuple[str, str, str]]:
        """Yield (page_url, html, content_hash) for up to source.max_pages pages."""
        max_pages = max(1, int(getattr(source, "max_pages", 1) or 1))
        template = getattr(source, "page_url_template", "") or ""
        selector = getattr(source, "next_page_selector", "") or ""
        visited: set[str] = set()
        seen_hashes: set[str] = set()
        url = source.url
        for page_no in range(1, max_pages + 1):
            if template and page_no > 1:
                url = template.replace("{page}", str(page_no))
            norm = normalize_url(url)
            if norm in visited:
                return
            visited.add(norm)
            html, content_hash, final_url = _fetch_html(self.http, self.browser, source, url)
            if not html:
                return
            # Sites that ignore the page parameter re-serve page 1 forever.
            if content_hash and content_hash in seen_hashes:
                logger.debug("Pagination for %s repeated page %s content; stopping", source.name, url)
                return
            seen_hashes.add(content_hash)
            link_base = final_url or url
            yield url, html, content_hash, link_base
            if page_no >= max_pages or template:
                continue
            url = next_page_url(url, html, selector)
            if not url:
                return

    def discover(self, source: StateSource) -> Iterator[Candidate]:
        seen: set[str] = set()
        visited_links: set[str] = set()
        seen_texts: set[str] = set()
        doc_fetch_count = [0]
        context_parent = "tr" if source.link_selector else None
        extra_domains = list(getattr(source, "allowed_extra_domains", []) or [])
        for page_no, (page_url, html, content_hash, link_base) in enumerate(
            self._iter_pages(source), start=1
        ):
            links = self.http.extract_links(
                link_base,
                html,
                link_selector=source.link_selector,
                link_context_parent=context_parent,
                allowed_extra_domains=extra_domains,
            )
            template = getattr(source, "document_url_template", "") or ""
            if template:
                seen_urls = {link_url for link_url, _text, _ctx in links}
                for link_url, link_text, link_context in extract_table_document_links(html, template):
                    if link_url not in seen_urls:
                        links.append((link_url, link_text, link_context))
                        seen_urls.add(link_url)
            page_texts = {text for _url, text, _ctx in links}
            if page_no > 1 and not (page_texts - seen_texts):
                # Same items under a different path: several archives answer any
                # /page/N/ with page 1, which would otherwise mint phantom
                # duplicates of every document at ".../page/N/View?doc=...".
                logger.debug("Pagination for %s repeated page %s; stopping", source.name, page_url)
                break
            seen_texts |= page_texts
            for link_url, link_text, link_context in links:
                if link_url in visited_links:
                    continue
                visited_links.add(link_url)
                candidate = _candidate_from_link(
                    source,
                    link_url,
                    link_text,
                    content_hash,
                    link_context or "",
                    http=self.http,
                    doc_fetch_count=doc_fetch_count,
                )
                if candidate:
                    seen.add(candidate.url)
                    yield candidate
        for candidate in _candidates_from_sample_urls(source):
            if candidate.url not in seen:
                seen.add(candidate.url)
                yield candidate
        for candidate in _candidates_from_year_slug_templates(source, self.http):
            if candidate.url not in seen:
                seen.add(candidate.url)
                yield candidate


class SearchFetcher:
    def __init__(self, http: HttpFetcher, browser: "BrowserRenderer | None" = None):
        self.http = http
        self.browser = browser

    def discover(self, source: StateSource) -> Iterator[Candidate]:
        queries = source.search_queries or DEFAULT_SEARCH_QUERIES
        seen_urls: set[str] = set()
        doc_fetch_count = [0]
        search_base = source.search_url.split("{query}")[0].rstrip("?&")
        context_parent = "tr" if source.link_selector else None
        if not source.link_selector and not source.render_js:
            logger.warning(
                "Search source %s has no link_selector and render_js=false; "
                "page may be a JS shell yielding only nav chrome",
                source.name,
            )
        for query in queries:
            if source.browser_input_selector and source.browser_submit_selector:
                fetch_url = search_base or source.search_url
            else:
                fetch_url = source.build_search_url(query)
            results_norm = normalize_url(fetch_url)
            html, content_hash, final_url = _fetch_html(
                self.http,
                self.browser,
                source,
                fetch_url,
                method=source.http_method,
                query=query,
            )
            if not html:
                continue
            for link_url, link_text, row_context in self.http.extract_links(
                final_url or fetch_url,
                html,
                same_domain_only=False,
                link_selector=source.link_selector,
                link_context_parent=context_parent,
            ):
                if link_url in seen_urls:
                    continue
                # Skip same-page chrome (search results page linking to itself).
                if normalize_url(link_url) == results_norm:
                    continue
                seen_urls.add(link_url)
                candidate = _candidate_from_link(
                    source,
                    link_url,
                    link_text,
                    content_hash,
                    row_context or "",
                    search_query=query,
                    http=self.http,
                    doc_fetch_count=doc_fetch_count,
                )
                if candidate:
                    yield candidate
        for candidate in _candidates_from_sample_urls(source):
            if candidate.url not in seen_urls:
                seen_urls.add(candidate.url)
                yield candidate


class RssFetcher:
    ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

    def __init__(self, http: HttpFetcher):
        self.http = http

    def discover(self, source: StateSource) -> Iterator[Candidate]:
        body, content_hash, _final_url = self.http.fetch(source.rss_url, verify=source.ssl_verify)
        if not body:
            return
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            logger.warning("Invalid RSS for %s: %s", source.rss_url, exc)
            return

        items: list[ET.Element] = []
        if root.tag.endswith("rss"):
            channel = root.find("channel")
            if channel is not None:
                items = channel.findall("item")
        elif root.tag.endswith("feed"):
            items = root.findall("atom:entry", self.ATOM_NS) or root.findall("entry")

        for item in items:
            title = self._text(item, "title") or self._text(item, "atom:title", self.ATOM_NS)
            link = self._item_link(item)
            snippet = self._text(item, "description") or self._text(
                item, "summary"
            ) or self._text(item, "atom:summary", self.ATOM_NS) or title
            if not link:
                continue
            candidate = _candidate_from_link(source, link, title or link, content_hash, snippet)
            if candidate:
                if snippet and snippet != title:
                    candidate.snippet = snippet[:500]
                yield candidate

    def _text(self, item: ET.Element, tag: str, ns: dict | None = None) -> str:
        node = item.find(tag, ns or {}) if ns else item.find(tag)
        if node is not None and node.text:
            return node.text.strip()
        return ""

    def _item_link(self, item: ET.Element) -> str:
        link_node = item.find("link")
        if link_node is not None:
            href = link_node.get("href") or link_node.text
            if href:
                return href.strip()
        guid = item.find("guid")
        if guid is not None and guid.text:
            return guid.text.strip()
        return ""


class ApiFetcher:
    """Fetch candidates from JSON APIs (e.g. NY Open Legislation)."""

    def __init__(self, http: HttpFetcher):
        self.http = http

    def discover(self, source: StateSource) -> Iterator[Candidate]:
        api_key_env = getattr(source, "api_key_env", "") or ""
        api_key = os.getenv(api_key_env, "").strip() if api_key_env else ""
        if api_key_env and not api_key:
            logger.warning(
                "Skipping API source %s: env %s is not set",
                source.name,
                api_key_env,
            )
            return

        template = source.api_url_template or source.search_url
        queries = source.search_queries or DEFAULT_SEARCH_QUERIES
        seen_urls: set[str] = set()
        is_fr = is_federal_register_api(template)
        is_doj = is_doj_press_api(template)

        for query in queries:
            url = template.replace("{query}", quote(query, safe=""))
            if api_key:
                url = url.replace("{api_key}", quote(api_key, safe=""))
            max_pages = int(getattr(source, "max_pages", 0) or 0) or 5
            page_num = 0

            while url and page_num < max_pages:
                page_num += 1
                html, content_hash, _final_url = self.http.fetch(
                    url,
                    verify=source.ssl_verify,
                    ignore_robots=source.ignore_robots,
                    user_agent=source.user_agent,
                )
                if not html:
                    break
                try:
                    payload = json.loads(html)
                except json.JSONDecodeError as exc:
                    logger.warning("Invalid JSON from %s: %s", url, exc)
                    break

                if is_fr:
                    before = len(seen_urls)
                    yield from self._discover_federal_register(
                        source, payload, content_hash, query, seen_urls
                    )
                    if len(seen_urls) == before:
                        break
                    next_url = str(payload.get("next_page_url") or "").strip()
                    if not next_url:
                        break
                    url = next_url
                    continue

                if is_doj:
                    before = len(seen_urls)
                    yield from self._discover_doj_press(
                        source, payload, content_hash, query, seen_urls
                    )
                    if len(seen_urls) == before:
                        break
                    resultset = (payload.get("metadata") or {}).get("resultset") or {}
                    try:
                        total = int(resultset.get("count") or 0)
                    except (TypeError, ValueError):
                        total = 0
                    try:
                        current_page = int(resultset.get("page") or page_num)
                    except (TypeError, ValueError):
                        current_page = page_num
                    try:
                        page_size = int(resultset.get("pagesize") or 20)
                    except (TypeError, ValueError):
                        page_size = 20
                    if not payload.get("results") or current_page * page_size >= total:
                        break
                    next_page = current_page + 1
                    next_url = bump_page_url(url, next_page)
                    if not next_url:
                        sep = "&" if "?" in url else "?"
                        next_url = f"{url}{sep}page={next_page}"
                    url = next_url
                    continue

                if not payload.get("success"):
                    logger.warning(
                        "API error for %s: %s",
                        source.name,
                        payload.get("message", "unknown"),
                    )
                    break

                items = (payload.get("result") or {}).get("items") or []
                for item in items:
                    bill = item.get("result") if isinstance(item, dict) else None
                    if not isinstance(bill, dict):
                        bill = item if isinstance(item, dict) else {}
                    session = bill.get("session") or bill.get("year")
                    print_no = bill.get("basePrintNo") or bill.get("printNo")
                    if not session or not print_no:
                        continue
                    link_url = f"https://legislation.nysenate.gov/bills/{session}/{print_no}"
                    if link_url in seen_urls:
                        continue
                    seen_urls.add(link_url)
                    title = str(bill.get("title") or print_no)
                    summary = str(bill.get("summary") or "")
                    candidate = _candidate_from_link(
                        source,
                        link_url,
                        title,
                        content_hash,
                        summary[:500] if summary else "",
                        search_query=query,
                    )
                    if candidate:
                        yield candidate
                break

    def _discover_federal_register(
        self,
        source: StateSource,
        payload: dict,
        content_hash: str,
        query: str,
        seen_urls: set[str],
    ) -> Iterator[Candidate]:
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            link_url = str(item.get("html_url") or item.get("pdf_url") or "")
            if not link_url or link_url in seen_urls:
                continue
            seen_urls.add(link_url)
            title = str(item.get("title") or link_url)
            summary = federal_register_item_snippet(item)
            candidate = _candidate_from_link(
                source,
                link_url,
                title,
                content_hash,
                summary[:500] if summary else "",
                search_query=query,
            )
            if candidate:
                yield candidate

    def _discover_doj_press(
        self,
        source: StateSource,
        payload: dict,
        content_hash: str,
        query: str,
        seen_urls: set[str],
    ) -> Iterator[Candidate]:
        """Parse justice.gov /api/v1/press_releases.json responses."""
        meta = payload.get("metadata") or {}
        status = (meta.get("responseInfo") or {}).get("status")
        if status not in (None, 200, "200"):
            logger.warning("DOJ press API error for %s: status=%s", source.name, status)
            return
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            link_url = str(item.get("url") or "")
            if not link_url or link_url in seen_urls:
                continue
            seen_urls.add(link_url)
            title = str(item.get("title") or link_url)
            summary = str(item.get("teaser") or item.get("body") or "")
            # Strip crude HTML from teaser/body for snippet + keyword prescreen.
            if "<" in summary:
                summary = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
            candidate = _candidate_from_link(
                source,
                link_url,
                title,
                content_hash,
                summary[:500] if summary else "",
                search_query=query,
            )
            if candidate:
                yield candidate
