import requests
from urllib.parse import urlparse
import re
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
        return '.gov' in domain

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

            # Process other .gov URLs
            response = requests.get(url)
            print(f"Response status code: {response.status_code}")
            if response.status_code != 200:
                error_msg = f"Failed to retrieve .gov URL: HTTP {response.status_code}"
                print(error_msg)
                return None, error_msg

            content_type = response.headers.get('Content-Type', '')

            if 'text/html' in content_type:
                # Handle HTML content
                print("Processing HTML content.")
                decoded_text = self.document_processor.strip_html_tags(response.content)
            elif 'application/pdf' in content_type:
                # Handle PDF content
                print("Processing PDF content.")
                decoded_text = self.document_processor.extract_text_from_pdf(response.content)
            else:
                # Attempt to guess content type based on URL
                if url.endswith('.pdf'):
                    print("URL ends with .pdf, processing as PDF.")
                    decoded_text = self.document_processor.extract_text_from_pdf(response.content)
                else:
                    print("Defaulting to processing as HTML.")
                    decoded_text = self.document_processor.strip_html_tags(response.content)

            # Handle justice.gov-specific text processing
            if 'justice.gov' in url:
                print("URL is from justice.gov, removing content after 'Related Content'.")
                decoded_text = decoded_text.split('Related Content')[0]

            print("Document text retrieved successfully.")
            return decoded_text, None

        except Exception as e:
            error_msg = f"Error retrieving document text: {str(e)}"
            print(error_msg)
            return None, error_msg

