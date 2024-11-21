import re
import datetime
from urllib.parse import urlparse
from gpt_questions import ChatGPTQuestionnaire
from legiscan_processor import LegiScanProcessor
from gov_processor import GovProcessor
from titlecase import titlecase

# Assume GovProcessor is imported or defined in the same file

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
        self.gov_processor = GovProcessor(document_processor, indigenous_db)
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
            elif self.gov_processor.is_gov_url(url):
                print("URL identified as .gov URL.")
                # Handle .gov URL using GovProcessor
                decoded_text, error_msg = self.gov_processor.get_gov_document_text(url)
                if error_msg:
                    self.compiled_bill['error'] = error_msg
                    print(error_msg)
                    return False, error_msg

                # Since it's an executive order, we may not have a bill_id or doc_id
                self.compiled_bill['decoded_text'] = decoded_text
                self.compiled_bill['bill_id'] = None
                self.compiled_bill['doc_id'] = None
                self.compiled_bill['bill_text_url'] = url

                #print(f"Text retrieved: {decoded_text}")

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
        For .gov bills, retrieves additional state details.
        """
        if not bill_id:
            # For .gov URLs, check and process state and title details directly
            print(f"No bill ID found, attempting to get details via GPT")
            bill_link = self.compiled_bill.get('bill_text_url', '')
            print(f"Link returned from compiled bill for IF check: {bill_link}")
            bill_text = self.compiled_bill['decoded_text']

            if '.gov' in bill_link:
                try:
                    # Get state details via GPT
                    state_details = self.questionnaire.ask_state(bill_link)
                    print(f"State returned from GPT: {state_details}")
                    # Get title via GPT
                    title = self.questionnaire.ask_title(bill_text)
                    print(f"Title returned from GPT: {title}")

                    # Ensure title follows proper title case capitalization rules
                    title = titlecase(title)
                    print(f"Formatted Title: {title}")

                    # Save the state and title in the bill dictionary
                    bill_number = self.questionnaire.ask_bill_number(bill_text)
                    print(f"Bill number returned from GPT: {bill_number}")

                    chamber_details = self.questionnaire.ask_chamber_details(bill_text)
                    print(f"Chamber details returned from GPT: {chamber_details}")

                    session_title = self.questionnaire.ask_session(bill_text)
                    print(f"Session number returned from GPT: {session_title}")
                    session = {'session_title': session_title}

                    last_updated = self.questionnaire.ask_last_updated(chamber_details)
                    print(f"Last updated returned from GPT: {last_updated}")

                    # Save the details in the bill dictionary
                    self.compiled_bill['bill'] = {
                        'state': state_details,
                        'title': title,
                        'bill_number': bill_number,
                        'session': session,
                        'status_date': last_updated,
                    }

                    # Get chamber or department via GPT
                    chamber = self.questionnaire.ask_chamber(bill_text)
                    print(f"Chamber returned from GPT: {chamber}")

                    # Get sponsors via GPT
                    sponsors = self.questionnaire.ask_sponsors(bill_text)
                    print(f"Sponsors returned from GPT: {sponsors}")

                    # Define a function to split sponsors string, handling commas inside brackets
                    def split_sponsors(sponsors_string):
                        sponsors_list = []
                        bracket_level = 0
                        current_sponsor = ''
                        for char in sponsors_string:
                            if char == ',' and bracket_level == 0:
                                sponsors_list.append(current_sponsor.strip())
                                current_sponsor = ''
                            else:
                                if char == '[':
                                    bracket_level += 1
                                elif char == ']':
                                    if bracket_level > 0:
                                        bracket_level -= 1
                                current_sponsor += char
                        if current_sponsor:
                            sponsors_list.append(current_sponsor.strip())
                        return sponsors_list

                    # Use the function to split sponsors
                    sponsors_list = split_sponsors(sponsors)
                    print(f"Sponsors list after splitting: {sponsors_list}")

                    # Initialize lists to hold the processed sponsors
                    processed_sponsors = []
                    processed_indigenous_sponsors = []

                    # Process each sponsor to update ethnicity and replace role with `offices_held` if Indigenous
                    for sponsor in sponsors_list:
                        # Split the sponsor string into name and details using ' - ' as the delimiter
                        if ' - ' in sponsor:
                            parts = sponsor.split(' - ', 1)  # Split into two parts: name and details
                            name = parts[0].strip()
                            details = parts[1].strip()
                        else:
                            # If no ' - ', treat the entire string as the name with no details
                            name = sponsor.strip()
                            details = ''

                        # Extract additional details from parentheses if present
                        if '(' in details and ')' in details:
                            role = details.split('(')[0].strip()  # Role is before the first '('
                            additional_details = details[details.find('(') + 1:details.find(')')].strip()
                        else:
                            role = details
                            additional_details = ''

                        # Retrieve the ethnicity and offices_held by searching the database
                        indigenous_data = next(
                            (entry for entry in self.indigenous_db.database if entry['name'] == name),
                            None
                        )
                        ethnicity = indigenous_data.get('ethnicity') if indigenous_data else None
                        offices_held = indigenous_data.get('offices_held') if indigenous_data else None

                        if ethnicity and ethnicity != 'N/A':
                            # Replace the role with `offices_held` if available
                            if offices_held:
                                role = offices_held

                            # Move ethnicity after the name in parentheses
                            name_with_ethnicity = f"{name} ({ethnicity})"

                            # Build the complete sponsor string
                            if role and additional_details:
                                sponsor_with_ethnicity = f"{name_with_ethnicity} - {role} ({additional_details})"
                            elif role:
                                sponsor_with_ethnicity = f"{name_with_ethnicity} - {role}"
                            elif additional_details:
                                sponsor_with_ethnicity = f"{name_with_ethnicity} ({additional_details})"
                            else:
                                sponsor_with_ethnicity = name_with_ethnicity

                            # Add to Indigenous sponsors list
                            processed_indigenous_sponsors.append(sponsor_with_ethnicity)
                        else:
                            # Keep the sponsor as is
                            name_with_ethnicity = name  # No ethnicity for non-Indigenous sponsors
                            if role and additional_details:
                                sponsor_with_ethnicity = f"{name_with_ethnicity} - {role} ({additional_details})"
                            elif role:
                                sponsor_with_ethnicity = f"{name_with_ethnicity} - {role}"
                            elif additional_details:
                                sponsor_with_ethnicity = f"{name_with_ethnicity} ({additional_details})"
                            else:
                                sponsor_with_ethnicity = name_with_ethnicity

                        # Append to processed_sponsors list
                        processed_sponsors.append(sponsor_with_ethnicity)

                    # Join the processed sponsors lists into strings
                    processed_sponsors_string = ', '.join(processed_sponsors)
                    processed_indigenous_sponsors_string = ', '.join(processed_indigenous_sponsors)

                    # Store the strings in the compiled bill
                    self.compiled_bill['bill_sponsors'] = processed_sponsors_string
                    self.compiled_bill['indigenous_sponsors'] = processed_indigenous_sponsors_string

                    # Print the processed sponsors
                    print(f"Processed Sponsors: {processed_sponsors_string}")
                    print(f"Processed Indigenous Sponsors: {processed_indigenous_sponsors_string}")

                    # Update the class attributes if needed
                    self.indigenous_sponsors = processed_indigenous_sponsors_string

                    # Store applicable data in compiled_bill
                    self.compiled_bill.update({
                        'bill_passed_status': 'Passed',
                        'progression_status': 'Passed',
                        'chamber': chamber,
                        'chamber_details': chamber_details,
                        # 'bill_sponsors' and 'indigenous_sponsors' already updated above
                    })

                except Exception as e:
                    error_msg = f"Error retrieving state or title via GPT: {str(e)}"
                    self.compiled_bill['error'] = error_msg
                    print(error_msg)
                    return False, error_msg
            else:
                # Handle non-government bills appropriately
                self.compiled_bill['bill'] = {
                    'state': 'Not applicable',
                    'title': 'Unknown Title'
                }
            return True, "No bill ID provided; processed .gov URL for state and title details if applicable."

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

            centering_indigenous_voices_eval = self.questionnaire.ask_centering_indigenous_voices_eval(decoded_text, self.indigenous_sponsors)
            centering_indigenous_voices_expl = self.questionnaire.ask_centering_indigenous_voices_expl(decoded_text, self.indigenous_sponsors)

            print(f"FROM GPT -- Centering Indigenous Voices Evaluation: {centering_indigenous_voices_eval}")
            print(f"FROM GPT -- Centering Indigenous Voices Explaination: {centering_indigenous_voices_expl}")

            survivor_relative_input_eval = self.questionnaire.ask_survivor_relative_input_eval(decoded_text).strip(".")
            survivor_relative_input_expl = self.questionnaire.ask_survivor_relative_input_expl(decoded_text).strip(".")

            categories_eval = self.questionnaire.ask_categories_eval(decoded_text)

            # Format data points string to be used in pros and cons analysis
            data_points = (
                f"Chat Summary: {chat_summary}\n"
                f"Gender Inclusion: {gender_inclusive_expl}\n"
                f"Mechanisms Explained: {mechanisms_expl}\n"
                f"Prevention Efforts: {prevention_efforts_expl}\n"
                f"Indigenous Sponsors: {self.indigenous_sponsors}\n"

                f"Centering Indigenous Voices?: {centering_indigenous_voices_eval}\n"
                f"Centering Indigenous Voices: {centering_indigenous_voices_expl}\n"




                f"Level of Survivor / Relative Input?: {survivor_relative_input_eval}\n"
                f"Level of Survivor / Relative Input: {survivor_relative_input_expl}\n"

                f"Legislation Categories: {categories_eval}"
            )

            # Ask for pros and cons using formatted data points
            uic_pros = self.questionnaire.ask_uic_pros(data_points)
            uic_cons = self.questionnaire.ask_uic_cons(data_points)

            # Store the results in compiled_bill
            self.compiled_bill.update({
                'chat_summary': chat_summary,
                'gender_inclusive_eval': gender_inclusive_eval,
                'gender_inclusive_expl': gender_inclusive_expl,
                'mechanisms_eval': mechanisms_eval,
                'mechanisms_expl': mechanisms_expl,
                'prevention_efforts_eval': prevention_efforts_eval,
                'prevention_efforts_expl': prevention_efforts_expl,
                'centering_indigenous_voices_eval': centering_indigenous_voices_eval,
                'centering_indigenous_voices_expl': centering_indigenous_voices_expl,

                'survivor_relative_input_eval': survivor_relative_input_eval,
                'survivor_relative_input_expl': survivor_relative_input_expl,

                'categories_eval': categories_eval,
                'uic_pros': uic_pros,
                'uic_cons': uic_cons
            })

            print(f"FROM BILL OBJ -- Centering Indigenous Voices Evaluation: {self.compiled_bill.get('centering_indigenous_voices_eval')}")
            print(f"FROM BILL OBJ -- Centering Indigenous Voices Explaination: {self.compiled_bill.get('centering_indigenous_voices_expl')}")

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
                'Bill Number': bill.get('bill_number', '') or '',
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

                'Level of Survivor / Relative Input?': bill_info.get('survivor_relative_input_eval', ''),
                'Level of Survivor / Relative Input': bill_info.get('survivor_relative_input_expl', ''),

                'Centering of Indigenous Voices?': bill_info.get('centering_indigenous_voices_eval', ''),
                'Centering of Indigenous Voices': bill_info.get('centering_indigenous_voices_expl', ''),

                'Sponsors': self.compiled_bill.get('bill_sponsors', 'Executive Order'),
                'Indigenous Sponsorship': self.compiled_bill.get('indigenous_sponsors', ''),

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
        self.chat_client.reset_context()
        return True, "Processing completed successfully"