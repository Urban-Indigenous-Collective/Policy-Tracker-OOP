import requests
from urllib.parse import urlparse
import re

class GovProcessor:
    def __init__(self, document_processor, indigenous_db):
        self.document_processor = document_processor
        self.indigenous_db = indigenous_db

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

            # If the URL is from justice.gov, remove everything after "Related Content"
            if 'justice.gov' in url:
                print("URL is from justice.gov, removing content after 'Related Content'.")
                # Split the text at "Related Content" and keep the part before it
                decoded_text = decoded_text.split('Related Content')[0]

            print(".gov document text retrieved successfully.")
            return decoded_text, None
        except Exception as e:
            error_msg = f"Error retrieving .gov document text: {str(e)}"
            print(error_msg)
            return None, error_msg


    def identify_indigenous_sponsors(self, sponsors_string):
        # Split the sponsors string into individual sponsors
        sponsor_list = re.split(r',\s*(?![^[]*[\]])', sponsors_string)

        indigenous_sponsors = []
        print(f"Indigenous sponsors list: {sponsor_list}")

        for sponsor in sponsor_list:
            if self.indigenous_db.is_indigenous_sponsor(sponsor):
                print(f"Sponsor as pulled from DB: {sponsor}")
                indigenous_sponsors.append(sponsor)

        return indigenous_sponsors

