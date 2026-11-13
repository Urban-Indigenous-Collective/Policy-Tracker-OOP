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

# DOJ press releases render these after Akamai bm-verify clears.
JUSTICE_GOV_WAIT_SELECTOR = "h1, article, .usa-prose"


def looks_like_hard_bot_deny(html: str) -> bool:
    """True for hard Access Denied / EdgeSuite blocks that will not recover."""
    if not html:
        return False
    lowered = html.lower()
    if "<title>access denied</title>" in lowered or "errors.edgesuite.net" in lowered:
        return True
    if "access denied" in lowered and "permission to access" in lowered:
        return True
    return False


def looks_like_soft_bot_challenge(html: str) -> bool:
    """True for Akamai Bot Manager interstitials that may clear after JS/meta-refresh."""
    if not html:
        return False
    lowered = html.lower()
    # ~2.5KB shell with meta-refresh to ?bm-verify=...
    if len(html) < 8000 and "bm-verify" in lowered:
        return True
    return False


def looks_like_bot_wall(html: str) -> bool:
    """True when HTML is an Akamai/EdgeSuite challenge or Access Denied page."""
    return looks_like_hard_bot_deny(html) or looks_like_soft_bot_challenge(html)


class BrowserRenderer:
    """Render pages with Playwright Chromium (lazy-started, reused per crawl run)."""

    def __init__(self, user_agent: str, headless: bool = True):
        self.user_agent = user_agent
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._unavailable_reason = ""

    @property
    def available(self) -> bool:
        return self._browser is not None

    def start(self) -> bool:
        """Start Chromium; return False when Playwright is missing or launch fails."""
        if self._browser is not None:
            return True
        if self._unavailable_reason:
            return False
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._unavailable_reason = (
                "Playwright is required for render_js sources. "
                "Install with: pip install playwright && playwright install chromium"
            )
            logger.error(self._unavailable_reason)
            return False
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=_STEALTH_ARGS,
            )
            logger.info("Playwright browser started")
            return True
        except Exception as exc:
            self._unavailable_reason = f"Playwright browser launch failed: {exc}"
            logger.error(self._unavailable_reason)
            self.stop()
            return False

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

    def _wait_out_soft_challenge(self, page, url: str, timeout_ms: int) -> None:
        """Wait for bm-verify interstitial to navigate away (meta-refresh ~5s + JS)."""
        try:
            page.wait_for_function(
                "() => !document.documentElement.outerHTML.toLowerCase().includes('bm-verify')",
                timeout=min(timeout_ms, 20000),
            )
        except Exception as exc:
            logger.warning("Browser soft challenge wait timed out for %s: %s", url, exc)

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
        if not self.start():
            return "", ""
        context, page = self._new_page(ignore_https, user_agent)
        html = ""
        try:
            # Soft challenges need network activity (meta-refresh / XHR); hard pages
            # with wait_selector can use networkidle once past the interstitial.
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            early = page.content()
            # Hard Access Denied never recovers — bail early.
            if looks_like_hard_bot_deny(early):
                logger.warning("Browser hit hard bot deny for %s (len=%s)", url, len(early))
                return "", ""
            # Soft bm-verify shells often clear after JS + ~5s meta-refresh. Do NOT
            # treat them as final failure before waiting (prod Docker early-exit bug).
            if looks_like_soft_bot_challenge(early):
                logger.info(
                    "Browser soft bot challenge for %s (len=%s); waiting for real content",
                    url,
                    len(early),
                )
                self._wait_out_soft_challenge(page, url, timeout_ms)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=min(timeout_ms, 20000))
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
        if not self.start():
            return "", ""
        context, page = self._new_page(ignore_https, user_agent)
        html = ""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            early = page.content()
            if looks_like_hard_bot_deny(early):
                logger.warning("Browser search hit hard bot deny for %s", url)
                return "", ""
            if looks_like_soft_bot_challenge(early):
                self._wait_out_soft_challenge(page, url, timeout_ms)
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
