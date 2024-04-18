import re
import datetime
from bs4 import BeautifulSoup



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
        Retrieves the bill ID from the LegiScan URL.
        """
        bill_id = self.extract_bill_id(legiscan_url)
        if not bill_id:
            return "Invalid LegiScan URL", None

        """
        Retrieves the text from the LegiScan URL.
        """
        decoded_text = self.get_bill_id_and_text(bill_id)

        bill_details = self.api_client.get_bill_details(self.bill_id)

        print("summarizing bill")
        bill_text_data = self.api_client.get_bill_text(bill_id)
        self.bill = bill_details['bill']
        bill_sponsors = ', '.join([f"{s['role']} {s['name']} ({s['party']}) - District {s['district']}" for s in self.bill['sponsors']])
        self.indigenous_sponsors = self.identify_indigenous_sponsors(bill_sponsors, self.indigenous_db)

        chat_summary = self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Please carefully evaluate the following legislation, and do not respond before analyzing it -- this pertains to each question I will ask. \n\n {decoded_text} \n\n Please summerize the aformentioned legislation in in 5 sentences or less."
            )
    
        mechanisms_eval = self.chat_client.get_chat_response(
            f"Do not decide if the text contains prevention efforts before reading the following question, and then carefully evaluating the legislation. Take your time. Can you quote the previously mentioned legislation includes mechanisms for evaluation? These could include but are not limited to a final report, consultation with community, tribal consulation, a Tribal Crisis Response Plan (TCRP), monitoring, or data collection. Do not include training as a mechanism for evaluation. Respond with only Yes or No. \n\n"
            )
        mechanisms_eval = mechanisms_eval.strip(".")

        mechanisms_expl = self.chat_client.get_chat_response(
            f"Based on your answer to the previous question, please quote the previously mentioned legislation where it mentions the specific mechanisms for evaluation (a final report, consultation with community, tribal consulation, a Tribal Crisis Response Plan (TCRP), monitoring, or data collection). Create a numbered list of ALL mechanisms of evaluation. \n\n"
            )

        
        #self.chat_client.conversation_history = []

        
        gender_inclusive_eval = self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Do not respond before reading the following question and then reviewing this legislation: \n\n {decoded_text} \n\n Does the previously mentioned legislation use gender inclusive language? This may include expanding Missing and Murdered Indigenous Womens crisis to refer to missing Indigenous people in general, or simply using gender neutral language throughout. Reply simply with Yes or No \n\n"
            )
        gender_inclusive_eval = gender_inclusive_eval.strip(".")
        gender_inclusive_expl = self.chat_client.get_chat_response(
            f"Does the previously mentioned legislation use gender inclusive language? This may include expanding Missing and Murdered Indigenous Womens crisis to refer to missing Indigenous people in general, or simply using gender neutral language throughout. Explain why in 3 sentences or less. Do not restate the original question in your answer. \n\n"
            )

        
        #self.chat_client.conversation_history = []



        prevention_efforts_eval = self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Do not respond before fully reading the following question and then reviewing this legislation: \n\n {decoded_text} \n\n Take your time and be accurate. Please evaluate the previously mentioned legislation for any prevention efforts regarding Missing and Murdered Indigenous Persons, including but not limited to training or awareness efforts. Double check your work before answering. Please answer with just Yes or No \n\n"
            )
        prevention_efforts_eval = prevention_efforts_eval.strip(".")

        prevention_efforts_expl = self.chat_client.get_chat_response(
            f"Do not respond before reading the question, and then reviewing the legislation closely. Take your time and be accurate. Please evaluate the previously mentioned legislation for any prevention efforts regarding Missing and Murdered Indigenous Persons including but not limited to training or awareness efforts. If any prevention efforts are identified, please quote the text and return the quoted text. If no prevention efforts can be identified, please return \”No\”."
            )                        
        

        #self.chat_client.conversation_history = []



        centering_indigenous_voices = self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Do not respond before fully reading the following question and then reviewing this legislation: \n\n {decoded_text} \n\n Take your time and be accurate. Please evaluate the previously mentioned legislation for the level of input from MMIP survivors, relatives of MMIP survivors, Indigenous politicians, and Indigenous communities in general in the following legislation. The following Indigenous politicans are sponsoring the legislation: {self.indigenous_sponsors} \n\n Double check your work before answering. Please return either No, Somewhat, and Yes alongside a 3 sentence (or less) explaination. If no mention is made, return No. \n\n"
            ) 

        survivor_relative_input_eval = self.chat_client.get_chat_response(
            f"Do not respond before fully reading the following question and then reviewing the previously mentioned legislation. Take your time and be accurate. Please evaluate the previously mentioned legislation for the level of input from MMIP survivors or relatives of MMIP survivors in the following legislation. Please return either No, Somewhat, or Yes. Do not include an explaination. If no mention is made, return No. \n\n"
            ) 
        survivor_relative_input_eval = survivor_relative_input_eval.strip(".")


        categories_eval = self.chat_client.get_chat_response(
            f"Please evaluate the previously mentioned legislation and return the most applicable categories in a comma seperated list: Taskforce, Day of Recognition, US Law Enforcement, Tribal Law Enforcement, Data Collection, MMIP Relatives \n\n"
            ) 


        uic_pros = self.chat_client.get_chat_response(
            f"Using the following data points: \n\n {chat_summary} \n\n {mechanisms_expl} \n\n {gender_inclusive_expl} \n\n {prevention_efforts_expl} \n\n Indigenous sponsors: {self.indigenous_sponsors} \n\n {centering_indigenous_voices} \n\n legislation categories: {categories_eval} \n\n please summarize the benefits or pros of the the previously mentioned legislation."
            )

        uic_cons = self.chat_client.get_chat_response(
            f"Using the following data points: \n\n {chat_summary} \n\n {mechanisms_expl} \n\n {gender_inclusive_expl} \n\n {prevention_efforts_expl} \n\n Indigenous sponsors: {self.indigenous_sponsors} \n\n {centering_indigenous_voices} \n\n legislation categories: {categories_eval} \n\n please summarize the drawbacks or cons of the previoisly memtioned legislation \n\n"
            )


        print("\n\nCenters Indigenous voices? " + centering_indigenous_voices)
        print("\n\nIncludes survivor / relative input? " + survivor_relative_input_eval)
        
        self.chat_client.conversation_history = []



        

        return self.bill_id, decoded_text, chat_summary, gender_inclusive_eval, gender_inclusive_expl, mechanisms_eval, mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons


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



    def identify_indigenous_sponsors(self, sponsors, indigenous_db):
        sponsors = [name.strip() for name in sponsors.split(',')]
        indigenous_sponsors = []

        for sponsor in sponsors:
            print(sponsor)
            print(indigenous_db.is_indigenous_sponsor(sponsor))
            if indigenous_db.is_indigenous_sponsor(sponsor):
                indigenous_sponsors.append(sponsor)
        return indigenous_sponsors


    def parse_bill_object(self, bill_details, bill, bill_text, bill_text_url, chat_response, gender_inclusive_response, gender_inclusive_explanation, mechanisms_eval,  mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons):
        
        #get_bill_details = self.api_client.get_bill_details(bill_id)

        bill_passed_status = self.check_bill_status(bill_details)  # For example usage


        
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
