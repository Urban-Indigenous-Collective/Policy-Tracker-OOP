import re
import datetime
from bs4 import BeautifulSoup
from gpt_questions import ChatGPTQuestionnaire
from legiscan_processor import LegiScanProcessor


class BillProcessor:
    def __init__(self, api_client, chat_client, document_processor, indigenous_db):
        self.api_client = api_client
        self.chat_client = chat_client
        self.document_processor = document_processor
        self.indigenous_sponsosors = ""
        self.indigenous_db = indigenous_db
        self.decoded_text = ""
        self.bill_id = ""
        self.bill = ""
        self.doc_id = ""
        self.questionnaire = ChatGPTQuestionnaire(chat_client)
        self.legiscan_processor = LegiScanProcessor(indigenous_db, self.api_client)

    def strip_html_tags(self, html_content):
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text()
    
    def extract_bill_id(self, url):
        """
        Extracts bill ID from a given URL.
        """
        print(f"Extracting bill ID from URL: {url}")
        match = re.search(r'/id/(\d+)', url)
        if match:
            print(f"Found bill ID: {match.group(1)}")
            return match.group(1)
        else:
            print("No bill ID found in URL.")
            return None


    def get_bill_id_and_text(self, bill_id, doc_id=None):
        """
        Fetches the bill text data using the bill ID and stores the document ID. If a document ID is provided, it uses that instead.
        """
        # Step 1: Use the provided doc_id if available
        if doc_id:
            print(f"Using provided document ID: {doc_id}")
            self.doc_id = doc_id
        else:
            # Fetch the bill details to find the document ID
            bill_details = self.api_client.get_bill_details(bill_id)

            # Check if bill_details contains the expected nested 'bill' and 'texts' keys
            if not bill_details or 'bill' not in bill_details or 'texts' not in bill_details['bill']:
                print("Error: Bill text data not available or no documents found.")
                return "Error: Bill text data not available", None

            # Extract the last document entry and store the document ID
            last_doc = bill_details['bill']['texts'][-1]
            self.doc_id = last_doc.get('doc_id')
            print(f"Retrieved document ID from bill details: {self.doc_id}")

        print(f"Getting text with doc id: {self.doc_id}")
        # Step 2: Fetch the actual bill text using the determined document ID
        bill_text_data = self.api_client.get_bill_text(self.doc_id)

        if not bill_text_data or 'doc' not in bill_text_data:
            print("Error: Bill text data not available or document missing.")
            return "Error: Bill text data not available", None

        # Process the document based on its MIME type
        mime_type = bill_text_data.get("mime")
        print(f"MIME type of the document: {mime_type}")

        if mime_type == "text/html":
            # Decode and strip HTML tags
            html_text = self.document_processor.decode_base64(bill_text_data["doc"])
            self.decoded_text = html_text.decode('latin-1')  # Ensure correct decoding
            self.decoded_text = self.strip_html_tags(self.decoded_text)
            return self.decoded_text, self.doc_id

        elif mime_type == "application/pdf":
            # Decode and extract text from PDF
            pdf_data = self.document_processor.decode_base64(bill_text_data['doc'])
            self.decoded_text = self.document_processor.extract_text_from_pdf(pdf_data)
            return self.decoded_text, self.doc_id

        else:
            print("Error: Document format not supported or missing.")
            return "Error: Document format not supported or missing", None

            
    def summarize_bill_text(self, legiscan_url, doc_id=None):
        """
        Retrieves and processes bill text from LegiScan.
        """
        # Use the passed-in doc_id if available
        print(f"Retrieved doc ID: {doc_id}")
        if doc_id:
            # Get bill text details using the doc_id
            bill_text_details = self.api_client.get_bill_text(doc_id)
            self.bill_id = bill_text_details.get('bill_id')
            print(f"Bill ID retrieved from bill text details: {self.bill_id}")
            if not self.bill_id:
                return "Invalid or Unavailable LegiScan URL", None
        else:
            # Retrieve bill_id from the URL
            self.bill_id = self.legiscan_processor.process_legiscan_url(legiscan_url)
            print(f"Bill ID returned from initial fetch: {self.bill_id}")
            if not self.bill_id:
                return "Invalid or Unavailable LegiScan URL", None

        # Retrieve the bill text using the provided doc_id or fetch it
        decoded_text, self.doc_id = self.get_bill_id_and_text(self.bill_id, doc_id=doc_id)

        print(f"Bill ID sent to API for details: {self.bill_id}")
        # Retrieve the bill details
        bill_details = self.api_client.get_bill_details(self.bill_id)

        # Ensure bill is available in the details
        self.bill = bill_details.get('bill', {})

        # Extract sponsors
        bill_sponsors = ', '.join([f"{s['role']} {s['name']} ({s['party']}) - District {s['district']}" for s in self.bill.get('sponsors', [])])
        self.indigenous_sponsors = self.legiscan_processor.identify_indigenous_sponsors(bill_sponsors)

        # Initialize all the return values with default None values to ensure there are no missing values
        chat_summary = self.questionnaire.ask_summary(decoded_text) if decoded_text else None
        gender_inclusive_eval = self.questionnaire.ask_gender_inclusive_eval(decoded_text).strip(".") if decoded_text else None
        gender_inclusive_expl = self.questionnaire.ask_gender_inclusive_expl(decoded_text) if decoded_text else None
        mechanisms_eval = self.questionnaire.ask_mechanisms_eval(decoded_text).strip(".") if decoded_text else None
        mechanisms_expl = self.questionnaire.ask_mechanisms_expl(decoded_text) if decoded_text else None
        prevention_efforts_eval = self.questionnaire.ask_prevention_efforts_eval(decoded_text).strip(".") if decoded_text else None
        prevention_efforts_expl = self.questionnaire.ask_prevention_efforts_expl(decoded_text) if decoded_text else None
        centering_indigenous_voices = self.questionnaire.ask_centering_indigenous_voices(decoded_text, self.indigenous_sponsors) if decoded_text else None
        survivor_relative_input_eval = self.questionnaire.ask_survivor_relative_input_eval(decoded_text).strip(".") if decoded_text else None
        categories_eval = self.questionnaire.ask_categories_eval(decoded_text) if decoded_text else None
        uic_pros = self.questionnaire.ask_uic_pros(decoded_text) if decoded_text else None
        uic_cons = self.questionnaire.ask_uic_cons(decoded_text) if decoded_text else None

        # Return results
        return self.bill_id, decoded_text, chat_summary, gender_inclusive_eval, gender_inclusive_expl, mechanisms_eval, mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons

    def parse_bill_object(self, bill_details, bill, bill_text, bill_text_url, chat_response, gender_inclusive_response, gender_inclusive_explanation, mechanisms_eval,  mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons):
            
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

        # Construct the bill data dictionary
        bill_data = {
            'State': bill['state'],
            'Title': bill['title'],
            'Bill Number': bill['bill_number'],
            'Status': bill_passed_status,  # Get status from the processor
            'Progression': status_codes.get(bill['status'], 'Unknown Status'),  # Use status code mapping from processor

            'Chamber': chamber,  # Get chamber name
            'Chamber Details': chamber_details,  # Get latest action details

            'Bill Overview': link,  # Get bill link
            'Bill Text': bill_text_url,
            'Optional Link': "",

            'Summary': chat_response,

            'UIC Pros': uic_pros,
            'UIC Cons': uic_cons,           

            'Mechanisms for Evaluation?': mechanisms_eval,
            'Mechanisms for Evaluation': mechanisms_expl,

            'Gender Inclusive Language?': gender_inclusive_response,
            'Gender Inclusive Explanation': gender_inclusive_explanation,

            'Prevention Efforts?': prevention_efforts_eval,
            'Prevention Efforts': prevention_efforts_expl,

            'Level of Survivor / Relative Input': survivor_relative_input_eval,
            'Centering of Indigenous Voices': centering_indigenous_voices,

            'Sponsors': ', '.join([f"{s['role']} {s['name']} ({s['party']}) - District {s['district']}" for s in bill['sponsors']]),
            'Indigenous Sponsorship': ', '.join(self.indigenous_sponsors),

            'Session': bill['session']['session_title'],
            'Categories': categories_eval,
            'Last Update': bill['status_date'],
        }

        return bill_data