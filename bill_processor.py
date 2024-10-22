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
        self.questionnaire = ChatGPTQuestionnaire(chat_client)
        self.legiscan_processor = LegiScanProcessor(indigenous_db)

    def strip_html_tags(self, html_content):
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text()
    
    def extract_bill_id(self, url):
        """
        Extracts bill ID from a given URL.
        """
        match = re.search(r'/id/(\d+)', url)
        return match.group(1) if match else None

    def get_bill_id_and_text(self, bill_id):
        
        bill_text_data = self.api_client.get_bill_text(bill_id)
        #Switch bill id from bill text, to bill listing
        self.bill_id = bill_text_data['bill_id']

        if bill_text_data:
            # Determine document format and decode appropriately
            if bill_text_data.get("mime") == "text/html":
                html_text = self.document_processor.decode_base64(bill_text_data["doc"])
                self.decoded_text = html_text.decode('latin-1')
                self.decoded_text = self.strip_html_tags(self.decoded_text)
                print(self.decoded_text)
                return self.decoded_text
            elif 'doc' in bill_text_data:
                pdf_data = self.document_processor.decode_base64(bill_text_data['doc'])
                self.decoded_text = self.document_processor.extract_text_from_pdf(pdf_data)
                return self.decoded_text

            else:
                return "Error: Document format not supported or missing", None
        else:
            return "Bill text data not available", None


    def summarize_bill_text(self, legiscan_url):
        """
        Retrieves and processes bill text from LegiScan.
        """
        # Retrieve the bill ID
        bill_id = self.extract_bill_id(legiscan_url)
        if not bill_id:
            return "Invalid LegiScan URL", None

        # Retrieve the bill text
        decoded_text = self.get_bill_id_and_text(bill_id)

        # Retrieve the bill details
        bill_details = self.api_client.get_bill_details(bill_id)

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


        # Correct return statement with all 14 values in the expected order
        return self.bill_id, decoded_text, chat_summary, gender_inclusive_eval, gender_inclusive_expl, mechanisms_eval, mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons


    def parse_response(self, text):
        # Normalize text to simplify matching
        lower_text = text.lower()
        
        # Check for explicit mentions of "yes," "somewhat," or "no"
        if " yes" in lower_text or lower_text.endswith("yes"):
            return "Yes"
        elif " somewhat" in lower_text or lower_text.endswith("somewhat"):
            return "Somewhat"
        elif " no" in lower_text or lower_text.endswith("no"):
            return "No"
        
        # If none of the explicit keywords are found, you might add more sophisticated logic here
        # For now, we'll return a default response indicating uncertainty

        # Example usage
        text = "It appears that the legislation does involve input from MMIP survivors or relatives, as it discusses the establishment of a study committee with members who are of indigenous descent or who actively work on issues relating to indigenous peoples. Therefore, the level of input from MMIP survivors or relatives in this legislation is Yes."
        print(text)


        return "Uncertain"



    def parse_bill_object(self, bill_details, bill, bill_text, bill_text_url, chat_response, gender_inclusive_response, gender_inclusive_explanation, mechanisms_eval,  mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons):
        
        #get_bill_details = self.api_client.get_bill_details(bill_id)

        #bill_passed_status = self.check_bill_status(bill_details)  # For example usage
        bill_passed_status = self.legiscan_processor.check_bill_status(bill_details)  # For example usage


        
        status_codes = {
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

    # Extract chamber from the first vote
        # Assuming 'bill' is the JSON object containing the bill information
        current_body_short = bill.get('body', 'N/A')

        # Map the short code to the full name of the chamber
        chamber_full_names = {
            'A': 'House',  # Assuming 'A' stands for Assembly --> Standardize lower chamber to House
            'S': 'Senate',
            'H': 'House',  # Added this line to handle cases where the current_body is 'H'
            'L': 'Legislative Body',  # Assuming 'U' could be used for unicameral (e.g., Nebraska)
            'N/A': 'Not Available'  # Handle cases where chamber information is not available
        }

        # Get the full name of the chamber
        chamber = chamber_full_names.get(current_body_short, 'Unknown')  # Default to 'Unknown' if the chamber is not recognized

        print(chamber)

        # Extract latest action from the history
        history = bill.get('history', [])
        chamber_details = 'N/A'
        if history:
            latest_action = history[-1]  # Get the last action in the history
            action_text = latest_action.get('action', 'N/A')
            action_chamber = latest_action.get('chamber', 'N/A')
            action_date = latest_action.get('date', 'N/A')
            chamber_details = f"{action_date} - {action_chamber}: {action_text}"

        link = bill.get('url', 'N/A')  # Assuming 'url' is the correct field

        bill_data = {
            'State': bill['state'],
            'Title': bill['title'],
            'Bill Number': bill['bill_number'],
            'Status': bill_passed_status,  # This line is added
            'Progression': status_codes.get(bill['status'], 'Unknown Status'),

            'Chamber': chamber,
            'Chamber Details': chamber_details,

            'Bill Overview': link,
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
