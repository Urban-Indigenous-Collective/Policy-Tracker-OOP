"""Headless browser fetcher for JS-rendered state legislature pages."""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

# Chromium launch flags that reduce headless fingerprinting (Akamai/bot walls).
_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
]


def looks_like_bot_wall(html: str) -> bool:
    """True when HTML is an Akamai/EdgeSuite challenge or Access Denied page."""
    if not html:
        return False
    lowered = html.lower()
    if "<title>access denied</title>" in lowered or "errors.edgesuite.net" in lowered:
        return True
    # Bot Manager interstitial is tiny and redirects via bm-verify.
    if len(html) < 8000 and (
        "bm-verify" in lowered
        or ("access denied" in lowered and "permission to access" in lowered)
    ):
        return True
    return False


class BrowserRenderer:
    """Render pages with Playwright Chromium (lazy-started, reused per crawl run)."""

    def __init__(self, user_agent: str, headless: bool = True):
        self.user_agent = user_agent
        self.headless = headless
        self._playwright = None
        self._browser = None

    def start(self) -> None:
        if self._browser is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for render_js sources. "
                "Install with: pip install playwright && playwright install chromium"
            ) from exc
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=_STEALTH_ARGS,
        )
        logger.info("Playwright browser started")

    def stop(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _new_page(self, ignore_https: bool, user_agent: str | None):
        assert self._browser is not None
        context = self._browser.new_context(
            user_agent=user_agent or self.user_agent,
            ignore_https_errors=ignore_https,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        return context, page

    def fetch(
        self,
        url: str,
        wait_selector: str | None = None,
        ignore_https: bool = False,
        timeout_ms: int = 45000,
        settle_ms: int = 2000,
        user_agent: str | None = None,
    ) -> tuple[str, str]:
        """Return rendered HTML and content hash."""
        self.start()
        context, page = self._new_page(ignore_https, user_agent)
        html = ""
        try:
            wait_until = "networkidle" if wait_selector else "domcontentloaded"
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            # Early exit on Akamai deny — don't burn the full wait_selector timeout.
            early = page.content()
            if looks_like_bot_wall(early):
                logger.warning("Browser hit bot wall for %s (len=%s)", url, len(early))
                return "", ""
            if wait_selector:
                try:
                    # Cap wait so a soft-block does not stall the crawl for 45s+.
                    page.wait_for_selector(wait_selector, timeout=min(timeout_ms, 15000))
                except Exception as exc:
                    logger.warning("Browser wait selector timed out for %s: %s", url, exc)
            elif settle_ms:
                page.wait_for_timeout(settle_ms)
            html = page.content()
        except Exception as exc:
            logger.warning("Browser fetch failed for %s: %s", url, exc)
            try:
                html = page.content()
            except Exception:
                html = ""
        finally:
            context.close()
        if not html or looks_like_bot_wall(html):
            if html:
                logger.warning("Browser hit bot wall for %s (len=%s)", url, len(html))
            return "", ""
        content_hash = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()
        return html, content_hash

    def fetch_search(
        self,
        url: str,
        query: str,
        input_selector: str,
        submit_selector: str,
        click_selector: str | None = None,
        wait_selector: str | None = None,
        ignore_https: bool = False,
        timeout_ms: int = 45000,
        user_agent: str | None = None,
    ) -> tuple[str, str]:
        """Fill a JS search form and return rendered results HTML."""
        self.start()
        context, page = self._new_page(ignore_https, user_agent)
        html = ""
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            if looks_like_bot_wall(page.content()):
                logger.warning("Browser search hit bot wall for %s", url)
                return "", ""
            if click_selector:
                page.locator(click_selector).click()
            page.locator(input_selector).fill(query)
            page.locator(submit_selector).click()
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=min(timeout_ms, 15000))
                except Exception as exc:
                    logger.warning("Browser search wait timed out for %s: %s", url, exc)
            html = page.content()
        except Exception as exc:
            logger.warning("Browser search failed for %s (%r): %s", url, query, exc)
            try:
                html = page.content()
            except Exception:
                html = ""
        finally:
            context.close()
        if not html or looks_like_bot_wall(html):
            if html:
                logger.warning("Browser search hit bot wall for %s", url)
            return "", ""
        content_hash = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()
        return html, content_hash
