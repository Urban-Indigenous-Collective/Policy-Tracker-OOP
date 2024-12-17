import requests
from urllib.parse import urlparse
import re

class FederalRegisterAPI:
    def __init__(self):
        self.api_base_url = "https://www.federalregister.gov/api/v1"

    def is_federal_register_url(self, url):
        """
        Checks if the given URL belongs to the Federal Register.
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        return 'federalregister.gov' in domain

    def fetch_document(self, url):
        """
        Fetches document data from the Federal Register API and retrieves the raw text.
        """
        try:
            # Extract document ID from URL
            parsed_url = urlparse(url)
            path_segments = parsed_url.path.strip('/').split('/')
            document_id = next((segment for segment in path_segments if re.match(r"\d{4}-\d{5}", segment)), None)

            if not document_id:
                error_msg = "Document ID not found in the URL."
                print(error_msg)
                return None, error_msg

            # Construct the API endpoint
            api_endpoint = f"{self.api_base_url}/documents/{document_id}.json"
            print(f"Fetching document metadata from Federal Register API: {api_endpoint}")

            # Fetch metadata from the API
            response = requests.get(api_endpoint)
            if response.status_code != 200:
                error_msg = f"Failed to fetch from Federal Register API: HTTP {response.status_code}"
                print(error_msg)
                return None, error_msg

            document_data = response.json()

            # Retrieve the raw text URL
            raw_text_url = document_data.get("raw_text_url")
            if not raw_text_url:
                error_msg = "Raw text URL not available in the API response."
                print(error_msg)
                return None, error_msg

            # Fetch the raw text content
            print(f"Fetching raw text content from: {raw_text_url}")
            text_response = requests.get(raw_text_url)
            if text_response.status_code != 200:
                error_msg = f"Failed to fetch raw text content: HTTP {text_response.status_code}"
                print(error_msg)
                return None, error_msg

            #print("Raw text content retrieved successfully.")
            print(f"Raw text content retrieved successfully. \n\n {text_response.text}")

            return text_response.text, None

        except Exception as e:
            error_msg = f"Error fetching Federal Register document: {str(e)}"
            print(error_msg)
            return None, error_msg