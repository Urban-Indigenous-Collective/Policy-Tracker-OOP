import datetime
import re
import requests
from bs4 import BeautifulSoup


class LegiScanProcessor:

    def __init__(self, indigenous_db, api_client):
        self.indigenous_db = indigenous_db
        self.api_client = api_client

        self.status_codes = {
            0: "Pre-filed or pre-introduction",
            1: "Introduced",
            2: "Engrossed",
            3: "Enrolled",
            4: "Passed",
            5: "Vetoed",
            6: "Failed Limited support based on state",
            7: "Override Progress",
            8: "Chaptered Progress",
            9: "Refer Progress",
            10: "Report Pass Progress",
            11: "Report DNP Progress",
            12: "Draft Progress"
        }
        self.chamber_full_names = {
            'A': 'House',  # Assembly is standardized to House
            'S': 'Senate',
            'H': 'House',  # Handle 'H' as House
            'L': 'Legislative Body',  # Potentially for unicameral legislature
            'N/A': 'Not Available'  # Handle cases where chamber info is missing
        }

    def extract_doc_id(self, url):
        """
        Extracts doc ID from a given URL.
        """
        print(f"Extracting bill ID from URL: {url}")
        match = re.search(r'/id/(\d+)', url)
        if match:
            print(f"Found bill ID: {match.group(1)}")
            return match.group(1)
        else:
            print("No bill ID found in URL.")
            return None
            
    def is_legiscan_url(self, url):
        """
        Checks if the URL is a LegiScan link.
        """
        return "legiscan.com" in url

    def get_latest_bill_id(self, state_code, session_year, bill_number):
        """
        Fetches the bill ID for a given state, session year, and bill number using the LegiScan API.
        """
        api_key = self.api_client.get_api_key()

        # Step 1: Get the session list for the state
        session_list_url = f"https://api.legiscan.com/?key={api_key}&op=getSessionList&state={state_code}"
        print("Session URL requested " + session_list_url)
        response = requests.get(session_list_url)
        
        if response.status_code == 200:
            sessions = response.json().get('sessions', [])
            if sessions:
                # Find the session that matches the provided year
                matching_session = None
                for session in sessions:
                    if session['year_start'] <= session_year <= session['year_end']:
                        matching_session = session
                        break

                if matching_session:
                    latest_session_id = matching_session['session_id']
                    print(f"Found session ID: {latest_session_id} for {state_code} in year {session_year}")

                    # Step 2: Get the master list for the selected session
                    master_list_url = f"https://api.legiscan.com/?key={api_key}&op=getMasterList&id={latest_session_id}"
                    print("MasterList URL requested " + master_list_url)
                    response = requests.get(master_list_url)

                    if response.status_code == 200:
                        master_list = response.json().get('masterlist', {})

                        # Step 3: Search for the bill number in the master list
                        for key, bill_data in master_list.items():
                            if isinstance(bill_data, dict) and bill_data.get('number') == bill_number:
                                print(f"Found bill {bill_number} with bill_id: {bill_data['bill_id']}")
                                return bill_data['bill_id']  # Return the matching bill ID and doc ID
                        
                        print(f"No matching bill found for {bill_number} in session {session_year}")
                        return None
                    else:
                        print(f"Error fetching master list: {response.status_code}")
                        return None
                else:
                    print(f"No matching session found for year {session_year} in state {state_code}.")
                    return None
            else:
                print(f"No sessions found for the state: {state_code}")
                return None
        else:
            print(f"Error fetching session list: {response.status_code}")
            return None

    def process_legiscan_url(self, url):
        """
        Processes the LegiScan URL to extract the bill ID if present.
        If no bill ID is found, attempts to extract state, session year, and bill number.
        """
        # Attempt to extract bill ID directly
        bill_id = self.extract_doc_id(url)
        if bill_id:
            return bill_id

        # Attempt to extract state, bill number, and session year if bill ID is not found
        match = re.search(r'legiscan\.com/([A-Z]{2})/bill/([A-Z]+[0-9]+)/([0-9]{4})', url)
        if match:
            state_code = match.group(1)  # e.g., 'AK'
            bill_number = match.group(2)  # e.g., 'SB211'
            session_year = int(match.group(3))  # e.g., 2022
            
            # Get the bill ID by passing the state, session year, and bill number
            latest_bill_id = self.get_latest_bill_id(state_code, session_year, bill_number)
            
            if latest_bill_id:
                print(f"Found bill ID: {latest_bill_id}")
                return latest_bill_id
            else:
                print(f"No bill found for {bill_number} in {state_code} for year {session_year}")
                return None
        else:
            print("Invalid LegiScan URL format.")
            return None


    def identify_indigenous_sponsors(self, sponsors):
        """
        Identifies and returns a list of Indigenous sponsors from the given list of sponsors.
        """
        sponsors = [name.strip() for name in sponsors.split(',')]
        indigenous_sponsors = []

        for sponsor in sponsors:
            if self.indigenous_db.is_indigenous_sponsor(sponsor):
                indigenous_sponsors.append(sponsor)

        return indigenous_sponsors

    def check_bill_status(self, bill_details):
        """
        Checks the status of a bill.
        """
        if bill_details['bill']['completed'] == 1:
            return "Passed"
        else:
            today = datetime.date.today()
            session_end_year = bill_details['bill']['session']['year_end']
            session_end_date = datetime.date(session_end_year, 12, 31)

            if today > session_end_date:
                return "Failed"
            else:
                return "Pending"

    def get_chamber_details(self, bill):
        """
        Extracts the chamber details (full name of the chamber) from a bill.
        """
        current_body_short = bill.get('body', 'N/A')
        chamber = self.chamber_full_names.get(current_body_short, 'Unknown')
        return chamber

    def get_latest_action(self, bill):
        """
        Extracts the latest action details from a bill.
        """
        history = bill.get('history', [])
        if history:
            latest_action = history[-1]  # Get the most recent action
            action_text = latest_action.get('action', 'N/A')
            action_chamber = latest_action.get('chamber', 'N/A')
            action_date = latest_action.get('date', 'N/A')
            chamber_details = f"{action_date} - {action_chamber}: {action_text}"
        else:
            chamber_details = 'N/A'
        
        return chamber_details

    def get_bill_link(self, bill):
        """
        Extracts the URL link of the bill.
        """
        return bill.get('url', 'N/A')

    def get_bill_id_and_text(self, bill_id, doc_id=None, document_processor=None):
        """
        Fetches the bill text data using the bill ID and stores the document ID.
        If a document ID is provided, it uses that instead.
        """
        if doc_id:
            print(f"Using provided document ID: {doc_id}")
        else:
            bill_details = self.api_client.get_bill_details(bill_id)

            if not bill_details or 'bill' not in bill_details or 'texts' not in bill_details['bill']:
                print("Error: Bill text data not available or no documents found.")
                return "Error: Bill text data not available", None

            last_doc = bill_details['bill']['texts'][-1]
            doc_id = last_doc.get('doc_id')
            print(f"Retrieved document ID from bill details: {doc_id}")

        print(f"Getting text with doc id: {doc_id}")
        bill_text_data = self.api_client.get_bill_text(doc_id)

        if not bill_text_data or 'doc' not in bill_text_data:
            print("Error: Bill text data not available or document missing.")
            return "Error: Bill text data not available", None

        mime_type = bill_text_data.get("mime")
        print(f"MIME type of the document: {mime_type}")

        if mime_type == "text/html":
            html_text = document_processor.decode_base64(bill_text_data["doc"])
            decoded_text = html_text.decode('latin-1')
            decoded_text = document_processor.strip_html_tags(decoded_text)
            return decoded_text, doc_id

        elif mime_type == "application/pdf":
            pdf_data = document_processor.decode_base64(bill_text_data['doc'])
            decoded_text = document_processor.extract_text_from_pdf(pdf_data)
            return decoded_text, doc_id

        else:
            print("Error: Document format not supported or missing.")
            return "Error: Document format not supported or missing", None


    def get_legiscan_text(self, legiscan_url, doc_id=None, document_processor=None):
        """
        Retrieves the bill text from LegiScan using either a provided doc_id or by processing the URL to get the bill ID.
        """
        # Use the provided doc_id if available
        print(f"Retrieved doc ID: {doc_id}")
        bill_id = None

        if doc_id:
            # Get bill text details using the doc_id
            bill_text_details = self.api_client.get_bill_text(doc_id)
            bill_id = bill_text_details.get('bill_id')
            print(f"Bill ID retrieved from bill text details: {bill_id}")
            if not bill_id:
                return "Invalid or Unavailable LegiScan URL", None
        else:
            # Retrieve bill_id from the URL
            bill_id = self.process_legiscan_url(legiscan_url)
            print(f"Bill ID returned from initial fetch: {bill_id}")
            if not bill_id:
                return "Invalid or Unavailable LegiScan URL", None

        # Retrieve the bill text using the provided doc_id or fetch the doc_id and get the text
        decoded_text, doc_id = self.get_bill_id_and_text(
            bill_id, doc_id=doc_id, document_processor=document_processor)
        
        return decoded_text, bill_id, doc_id