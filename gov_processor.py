import requests
from urllib.parse import urlparse

class GovProcessor:
    def __init__(self, document_processor):
        self.document_processor = document_processor

    def is_gov_url(self, url):
        """
        Checks if the given URL is a .gov URL.
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        return '.gov' in domain

    def get_gov_document_text(self, url):
        """
        Retrieves and processes the document text from a .gov URL.
        """
        try:
            print(f"Processing .gov URL: {url}")
            response = requests.get(url)
            print(f"Response status code: {response.status_code}")
            if response.status_code != 200:
                error_msg = f"Failed to retrieve .gov URL: HTTP {response.status_code}"
                print(error_msg)
                return None, error_msg

            content_type = response.headers.get('Content-Type', '')
            print(f"Content-Type: {content_type}")

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
                    # Handle PDF content
                    print("URL ends with .pdf, processing as PDF.")
                    response = requests.get(url)
                    decoded_text = self.document_processor.extract_text_from_pdf(response.content)
                else:
                    # Default to treating as HTML
                    print("Defaulting to processing as HTML.")
                    decoded_text = self.document_processor.strip_html_tags(response.content)

            print(".gov document text retrieved successfully.")
            return decoded_text, None
        except Exception as e:
            error_msg = f"Error retrieving .gov document text: {str(e)}"
            print(error_msg)
            return None, error_msg