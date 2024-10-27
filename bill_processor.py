import re
import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from gpt_questions import ChatGPTQuestionnaire
from legiscan_processor import LegiScanProcessor


class BillProcessor:
    def __init__(self, api_client, chat_client, document_processor, indigenous_db):
        self.api_client = api_client
        self.chat_client = chat_client
        self.document_processor = document_processor
        self.indigenous_sponsors = ""
        self.indigenous_db = indigenous_db
        self.decoded_text = ""
        self.bill_id = ""
        self.bill = ""
        self.doc_id = ""
        self.questionnaire = ChatGPTQuestionnaire(chat_client)
        self.legiscan_processor = LegiScanProcessor(indigenous_db, self.api_client)
        self.compiled_bill = {}

    def get_doc_text(self, url, doc_id=None):
        """
        Retrieves document text and relevant identifiers.
        Handles both LegiScan URLs and .gov URLs.
        """
        try:
            print(f"Getting document text from URL: {url}")
            if 'legiscan.com' in url:
                print("URL identified as LegiScan URL.")
                # Handle LegiScan URL
                decoded_text, bill_id, doc_id = self.legiscan_processor.get_legiscan_text(
                    url, doc_id=doc_id, document_processor=self.document_processor)
                
                if not bill_id:
                    error_msg = "Invalid or Unavailable LegiScan URL"
                    self.compiled_bill['error'] = error_msg
                    print(error_msg)
                    return False, error_msg

                # Store results in compiled_bill
                self.compiled_bill['decoded_text'] = decoded_text
                self.compiled_bill['bill_id'] = bill_id
                self.compiled_bill['doc_id'] = doc_id
                self.compiled_bill['bill_text_url'] = url

                print("LegiScan text retrieved successfully.")
                return True, "LegiScan text retrieved successfully"
            else:
                # Parse the URL to get the domain
                parsed_url = urlparse(url)
                domain = parsed_url.netloc
                print(f"Parsed domain: {domain}")
                if '.gov' in domain:
                    print("URL identified as .gov URL.")
                    # Handle .gov URL
                    response = requests.get(url)
                    print(f"Response status code: {response.status_code}")
                    if response.status_code != 200:
                        error_msg = f"Failed to retrieve .gov URL: HTTP {response.status_code}"
                        self.compiled_bill['error'] = error_msg
                        print(error_msg)
                        return False, error_msg

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

                    # Since it's an executive order, we may not have a bill_id or doc_id
                    self.compiled_bill['decoded_text'] = decoded_text
                    self.compiled_bill['bill_id'] = None
                    self.compiled_bill['doc_id'] = None
                    self.compiled_bill['bill_text_url'] = url

                    print(".gov document text retrieved successfully.")
                    return True, ".gov document text retrieved successfully"
                else:
                    error_msg = "Unsupported URL format"
                    self.compiled_bill['error'] = error_msg
                    print(error_msg)
                    return False, error_msg

        except Exception as e:
            error_msg = f"Error retrieving document text: {str(e)}"
            self.compiled_bill['error'] = error_msg
            print(error_msg)
            return False, error_msg


    def get_bill_details(self, bill_id):
        """
        Retrieves bill details using the bill ID and identifies Indigenous sponsors.
        """
        if not bill_id:
            # For .gov URLs, bill_id may be None
            self.compiled_bill['bill'] = None
            return True, "No bill details needed for .gov URL"

        try:
            bill_details = self.api_client.get_bill_details(bill_id)
            bill = bill_details.get('bill', {})

            # Extract sponsors and identify Indigenous sponsors
            bill_sponsors = ', '.join([f"{s['role']} {s['name']} ({s['party']}) - District {s['district']}" for s in bill.get('sponsors', [])])
            indigenous_sponsors = self.legiscan_processor.identify_indigenous_sponsors(bill_sponsors)

            # Use the LegiScanProcessor to get the bill status
            bill_passed_status = self.legiscan_processor.check_bill_status(bill_details)

            # Use the LegiScanProcessor to get chamber details
            chamber = self.legiscan_processor.get_chamber_details(bill)

            # Use the LegiScanProcessor to get the latest action details
            chamber_details = self.legiscan_processor.get_latest_action(bill)

            # Use the LegiScanProcessor to get the bill link
            link = self.legiscan_processor.get_bill_link(bill)

            # Define bill progression status
            status_codes = self.legiscan_processor.status_codes
            progression_status = status_codes.get(bill.get('status'), 'Unknown Status')

            # Store results in compiled_bill
            self.compiled_bill.update({
                'bill_details': bill_details,
                'bill': bill,
                'indigenous_sponsors': indigenous_sponsors,
                'bill_passed_status': bill_passed_status,
                'chamber': chamber,
                'chamber_details': chamber_details,
                'link': link,
                'progression_status': progression_status,
                'bill_sponsors': bill_sponsors
            })

            # Update instance variables
            self.bill = bill
            self.indigenous_sponsors = indigenous_sponsors

            return True, "Bill details retrieved successfully"
        except Exception as e:
            error_msg = f"Error retrieving bill details: {str(e)}"
            self.compiled_bill['error'] = error_msg
            return False, error_msg

    def summarize_bill_text(self):
        """
        Processes the bill text using the questionnaire.
        Assumes that 'decoded_text' and 'indigenous_sponsors' are already available in compiled_bill.
        """
        decoded_text = self.compiled_bill.get('decoded_text')
        if not decoded_text:
            error_msg = "No decoded text available for summarization."
            self.compiled_bill['error'] = error_msg
            return False, error_msg

        try:
            # Initialize all the return values with default None values to ensure there are no missing values
            chat_summary = self.questionnaire.ask_summary(decoded_text)
            gender_inclusive_eval = self.questionnaire.ask_gender_inclusive_eval(decoded_text).strip(".")
            gender_inclusive_expl = self.questionnaire.ask_gender_inclusive_expl(decoded_text)
            mechanisms_eval = self.questionnaire.ask_mechanisms_eval(decoded_text).strip(".")
            mechanisms_expl = self.questionnaire.ask_mechanisms_expl(decoded_text)
            prevention_efforts_eval = self.questionnaire.ask_prevention_efforts_eval(decoded_text).strip(".")
            prevention_efforts_expl = self.questionnaire.ask_prevention_efforts_expl(decoded_text)
            centering_indigenous_voices = self.questionnaire.ask_centering_indigenous_voices(decoded_text, self.indigenous_sponsors)
            survivor_relative_input_eval = self.questionnaire.ask_survivor_relative_input_eval(decoded_text).strip(".")
            categories_eval = self.questionnaire.ask_categories_eval(decoded_text)
            uic_pros = self.questionnaire.ask_uic_pros(decoded_text)
            uic_cons = self.questionnaire.ask_uic_cons(decoded_text)

            # Store the results in compiled_bill
            self.compiled_bill.update({
                'chat_summary': chat_summary,
                'gender_inclusive_eval': gender_inclusive_eval,
                'gender_inclusive_expl': gender_inclusive_expl,
                'mechanisms_eval': mechanisms_eval,
                'mechanisms_expl': mechanisms_expl,
                'prevention_efforts_eval': prevention_efforts_eval,
                'prevention_efforts_expl': prevention_efforts_expl,
                'centering_indigenous_voices': centering_indigenous_voices,
                'survivor_relative_input_eval': survivor_relative_input_eval,
                'categories_eval': categories_eval,
                'uic_pros': uic_pros,
                'uic_cons': uic_cons
            })

            return True, "Bill text summarized successfully"
        except Exception as e:
            error_msg = f"Error during summarization: {str(e)}"
            self.compiled_bill['error'] = error_msg
            return False, error_msg

    def parse_bill_object(self):
        """
        Parses the bill object to create a dictionary containing all necessary information.
        """
        try:
            # Use the data stored in compiled_bill
            bill_info = self.compiled_bill
            bill = bill_info.get('bill') or {}

            # Construct the bill data dictionary
            bill_data = {
                'State': bill.get('state', '') or 'Unknown',
                'Title': bill.get('title', '') or 'Executive Order',
                'Bill Number': bill.get('bill_number', '') or 'Executive Order',
                'Status': bill_info.get('bill_passed_status', 'Active'),  # Default to 'Active' for EOs
                'Progression': bill_info.get('progression_status', 'N/A'),

                'Chamber': bill_info.get('chamber', 'Executive'),
                'Chamber Details': bill_info.get('chamber_details', ''),

                'Bill Overview': bill_info.get('link', ''),
                'Bill Text': bill_info.get('bill_text_url', ''),
                'Optional Link': "",

                'Summary': bill_info.get('chat_summary', ''),

                'UIC Pros': bill_info.get('uic_pros', ''),
                'UIC Cons': bill_info.get('uic_cons', ''),

                'Mechanisms for Evaluation?': bill_info.get('mechanisms_eval', ''),
                'Mechanisms for Evaluation': bill_info.get('mechanisms_expl', ''),

                'Gender Inclusive Language?': bill_info.get('gender_inclusive_eval', ''),
                'Gender Inclusive Explanation': bill_info.get('gender_inclusive_expl', ''),

                'Prevention Efforts?': bill_info.get('prevention_efforts_eval', ''),
                'Prevention Efforts': bill_info.get('prevention_efforts_expl', ''),

                'Level of Survivor / Relative Input': bill_info.get('survivor_relative_input_eval', ''),
                'Centering of Indigenous Voices': bill_info.get('centering_indigenous_voices', ''),

                'Sponsors': bill_info.get('bill_sponsors', 'Executive Order'),
                'Indigenous Sponsorship': ', '.join(bill_info.get('indigenous_sponsors', [])),

                'Session': bill.get('session', {}).get('session_title', 'N/A'),
                'Categories': bill_info.get('categories_eval', ''),
                'Last Update': bill.get('status_date', datetime.datetime.now().strftime('%Y-%m-%d')),
            }

            # Store the final bill data
            self.compiled_bill['bill_data'] = bill_data

            return True, "Bill object parsed successfully"
        except Exception as e:
            error_msg = f"Error parsing bill object: {str(e)}"
            self.compiled_bill['error'] = error_msg
            print(error_msg)
            return False, error_msg


    def process_bill(self, url, doc_id=None):
        """
        Processes the bill through each step in order.
        """
        # Step 1: Get Document Text
        success, message = self.get_doc_text(url, doc_id=doc_id)
        if not success:
            print(message)
            return False, message

        # Step 2: Get Bill Details (if applicable)
        bill_id = self.compiled_bill.get('bill_id')
        success, message = self.get_bill_details(bill_id)
        if not success:
            print(message)
            return False, message

        # Step 3: Summarize Bill Text
        success, message = self.summarize_bill_text()
        if not success:
            print(message)
            return False, message

        # Step 4: Parse Bill Object
        success, message = self.parse_bill_object()
        if not success:
            print(message)
            return False, message

        print("Processing completed successfully.")
        return True, "Processing completed successfully"