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

            
    def summarize_bill_text(self, legiscan_url, doc_id=None):
        """
        Retrieves and processes bill text from LegiScan.
        """
        # Call get_legiscan_text to retrieve decoded text and IDs
        decoded_text, self.bill_id, self.doc_id = self.legiscan_processor.get_legiscan_text(
            legiscan_url, doc_id=doc_id, document_processor=self.document_processor)

        if not self.bill_id:
            return "Invalid or Unavailable LegiScan URL", None

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