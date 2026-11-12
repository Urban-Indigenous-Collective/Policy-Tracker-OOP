import requests
from urllib.parse import urlparse

from discovery.browser_fetcher import looks_like_bot_wall
from discovery.fetchers import (
    BROWSER_UA,
    HttpFetcher,
    extract_document_text,
    fetch_justice_gov_content,
    is_browser_gated_url,
)
from federal_register_client import FederalRegisterAPI


class GovProcessor:
    def __init__(self, document_processor, indigenous_db):
        self.document_processor = document_processor
        self.indigenous_db = indigenous_db
        self.federal_register_api = FederalRegisterAPI()

    def is_gov_url(self, url):
        """
        Checks if the given URL is a .gov URL.
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        return ".gov" in domain

    def get_gov_document_text(self, url):
        """
        Retrieves and processes the document text from a .gov URL or the Federal Register API.
        """
        try:
            print(f"Processing URL: {url}")

            # Check if the URL belongs to the Federal Register
            if self.federal_register_api.is_federal_register_url(url):
                print("URL identified as Federal Register. Fetching via API.")
                decoded_text, error = self.federal_register_api.fetch_document(url)
                if error:
                    return None, error
                return decoded_text, None

            # justice.gov / mass.gov: plain HTTP often returns an Akamai interstitial
            # shell (~2.5KB, empty title). Use the same HTTP→Playwright path as
            # discovery relevance so analysis sees the real press-release body.
            if is_browser_gated_url(url):
                print("URL is browser-gated; fetching via HTTP then Playwright.")
                http = HttpFetcher(BROWSER_UA)
                body, _content_hash, content_type = fetch_justice_gov_content(
                    http,
                    url,
                    user_agent=BROWSER_UA,
                )
                if not body:
                    error_msg = (
                        "Failed to retrieve browser-gated .gov URL "
                        "(bot wall or empty body after Playwright)"
                    )
                    print(error_msg)
                    return None, error_msg
                html = body.decode("utf-8", errors="replace")
                if looks_like_bot_wall(html):
                    error_msg = "Failed to retrieve browser-gated .gov URL: bot wall HTML"
                    print(error_msg)
                    return None, error_msg
                decoded_text = extract_document_text(body, url, content_type or "text/html")
                if "justice.gov" in url.lower() and decoded_text:
                    decoded_text = decoded_text.split("Related Content")[0]
                if not (decoded_text or "").strip():
                    error_msg = "Browser-gated .gov URL returned no extractable text"
                    print(error_msg)
                    return None, error_msg
                print("Document text retrieved successfully.")
                return decoded_text, None

            # Process other .gov URLs. Use a browser User-Agent so Akamai/Cloudflare
            # edges (michigan.gov, dojmt.gov, etc.) do not 403 the analysis fetch
            # after crawl relevance already succeeded with BROWSER_UA.
            response = requests.get(
                url,
                headers={"User-Agent": BROWSER_UA},
                timeout=60,
                allow_redirects=True,
            )
            print(f"Response status code: {response.status_code}")
            if response.status_code != 200:
                error_msg = f"Failed to retrieve .gov URL: HTTP {response.status_code}"
                print(error_msg)
                return None, error_msg

            content_type = response.headers.get("Content-Type", "")
            raw = response.content
            if looks_like_bot_wall(raw.decode("utf-8", errors="replace")):
                error_msg = f"Failed to retrieve .gov URL: bot wall HTML (HTTP {response.status_code})"
                print(error_msg)
                return None, error_msg

            if "text/html" in content_type:
                print("Processing HTML content.")
                decoded_text = self.document_processor.strip_html_tags(raw)
            elif "application/pdf" in content_type:
                print("Processing PDF content.")
                decoded_text = self.document_processor.extract_text_from_pdf(raw)
            else:
                if url.endswith(".pdf"):
                    print("URL ends with .pdf, processing as PDF.")
                    decoded_text = self.document_processor.extract_text_from_pdf(raw)
                else:
                    print("Defaulting to processing as HTML.")
                    decoded_text = self.document_processor.strip_html_tags(raw)

            print("Document text retrieved successfully.")
            return decoded_text, None

        except Exception as e:
            error_msg = f"Error retrieving document text: {str(e)}"
            print(error_msg)
            return None, error_msg
