# Import statements for each class
from api_client import APIClient
from bill_processor import BillProcessor
from document_processor import DocumentProcessor
from report_generator import ReportGenerator
from chatgpt_client import ChatGPTClient
from airtable_client import AirtableClient
from wikipedia_api_client import WikipediaAPIClient
from indigenous_database import IndigenousDatabase  # Import the IndigenousDatabase class
import time

class MainApplication:
    def __init__(self, legiscan_key, openai_key):
        self.api_client = APIClient(legiscan_key)
        self.chat_client = ChatGPTClient(openai_key)
        # Initialize Airtable Table
        self.airtable_client = AirtableClient()

        self.document_processor = DocumentProcessor()
        self.report_generator = ReportGenerator()
        self.wikipedia_client = WikipediaAPIClient()  # Initialize the WikipediaAPIClient
        self.indigenous_db = IndigenousDatabase()  # Initialize IndigenousDatabase
        print("Building Indigenous database...")
        self.indigenous_db.build_database()
        self.bill_processor = BillProcessor(self.api_client, self.chat_client, self.document_processor, self.indigenous_db)
        self.progress = 0  # Add this line to initialize progress tracking



    def run(self):
        print("Choose an option:")
        print("1 - Process LegiScan URLs")
        print("2 - Fetch data from List of Native American politicians")
        print("3 - Fetch data from Native American state legislators category")
        print("4 - Fetch data from Native Hawaiian politicians category")  # New option
        print("5 - Build Indigenous Politician Database")  # New option
        print("6 - Check if a list of politicians are Indigenous")  # New option


        choice = input("Enter choice: ").strip()

        if choice == "1":
            self.indigenous_db.build_database()

            urls = []
            print("Enter LegiScan URLs (type 'exit' to finish):")
            while True:
                url = input("Enter URL: ")
                if url.lower() == 'exit':
                    break
                urls.append(url)
            self.process_legiscan_urls(urls)

        elif choice == '2':
            list_url = "https://en.wikipedia.org/wiki/List_of_Native_American_politicians"
            politicians_list = WikipediaAPIClient().parse_list_page(list_url)
            #for politician in politicians_list:
            #    print(politician['name'])
            print(type(politicians_list))
            print(politicians_list)
            #print("STATE LIST?")
            #print(politicians_list)

        elif choice == '3':
            category_url = "Native_American_state_legislators"
            politicians_category = self.wikipedia_client.parse_category_and_subcategories(category_url)
            print(politicians_category)

        elif choice == '4':
            category_url = "Native_Hawaiian_politicians"
            politicians_category = self.wikipedia_client.parse_category_and_subcategories(category_url)
            print(politicians_category)
            print(type(politicians_category))

        elif choice == '5':
            self.indigenous_db.build_database()

        elif choice == '6':  # This is the option for checking Indigenous politicians
            if not self.indigenous_db.database:  # Check if the database is built
                print("Building database!")
                self.indigenous_db.build_database()

                print("calling new function")
                self.indigenous_db.print_database()

            while True:  # Start a loop to continuously ask for input
                politicians_input = input("Enter a comma-separated list of politicians, or type 'exit' to finish: ")
                if politicians_input.lower() == 'exit' or not politicians_input:
                    break  # Break the loop if 'exit' is entered or if the input is empty

                politicians_list = [name.strip() for name in politicians_input.split(',')]
                indigenous_politicians = []
                for politician in politicians_list:
                    if self.indigenous_db.is_indigenous_sponsor(politician):
                        indigenous_politicians.append(politician)
                if indigenous_politicians:
                    print("Indigenous Politicians: " + ', '.join(indigenous_politicians))
                else:
                    print("No Indigenous politicians found in the provided list.")





        else:
            print("Invalid choice")



    def check_politician_indigenous_status(self, politicians_list):
        """
        Checks if the given politicians are Indigenous based on the indigenous_db.
        :param politicians_list: List of politician names to check.
        :return: Dictionary with politician names as keys and a boolean indicating if they are Indigenous as values.
        """
        # Ensure the Indigenous database is built
        if not self.indigenous_db.database:
            print("Building Indigenous database...")
            self.indigenous_db.build_database()

        results = {}
        for politician in politicians_list:
            # Check if each politician is Indigenous
            is_indigenous = self.indigenous_db.is_indigenous_sponsor(politician)
            results[politician] = is_indigenous

        return results




    
    def process_urls_for_web(self, urls_string):
        urls = [url.strip() for url in urls_string.split(',')]
        total_urls = len(urls)

        # Reset progress at the start of processing
        self.progress = 0

        # Initialize a list to store processed data for each URL
        processed_data = []
        print(f"Starting URL processing. Total URLs: {total_urls}")


        for i, url in enumerate(urls):
            result = self.process_single_url(url)
            
            # Whether it's successful data or an error message, append it to processed_data
            processed_data.append(result)

            # Update and print progress
            self.progress = (i + 1) / total_urls * 100
            print(f"Processed URL {i+1}/{total_urls}. Current progress: {self.progress}%")
            time.sleep(1)

        # After processing all URLs, generate an Excel report
        if processed_data:
            excel_file_path = self.report_generator.export_to_excel(processed_data)
            print(excel_file_path)
            return excel_file_path
        else:
            return None  # Handle the case where no data was processed



    def get_progress(self):
        return self.progress

    def process_single_url(self, url):
        try:
            # Attempt to unpack the expected number of values
            print("Processing single url!")
            bill_id, bill_text, chat_summary, gender_inclusive_eval, gender_inclusive_expl, mechanisms_eval, mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons = self.bill_processor.summarize_bill_text(url)
            
            # Proceed if the correct number of items are unpacked
            if isinstance(bill_id, int):
                bill_details = self.api_client.get_bill_details(bill_id)
                if 'bill' in bill_details:
                    bill_data = self.bill_processor.parse_bill_object(bill_details, bill_details['bill'], bill_text, url, chat_summary, gender_inclusive_eval, gender_inclusive_expl, mechanisms_eval, mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons)
                    return bill_data
            else:
                print(bill_id)
                
        except ValueError as e:
            # Handle the error if the unpacking fails
            print(f"Error processing URL {url}: {e}")
            return {'url': url, 'error': f"Error processing URL: {str(e)}"}



#Old Method
    def process_legiscan_urls(self, urls):
        for legiscan_url in urls:
            bill_id, bill_text, chat_summary, gender_inclusive_eval, gender_inclusive_expl, mechanisms_eval, mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons = self.bill_processor.get_bill_id_and_text(legiscan_url)

            if isinstance(bill_id, int):
                bill_details = self.api_client.get_bill_details(bill_id)
                if 'bill' in bill_details:
                    bill_data = self.bill_processor.parse_bill_object(bill_details, bill_details['bill'], bill_text, legiscan_url, chat_summary, gender_inclusive_eval, gender_inclusive_expl, mechanisms_eval, mechanisms_expl, prevention_efforts_eval, prevention_efforts_expl, centering_indigenous_voices, survivor_relative_input_eval, categories_eval, uic_pros, uic_cons)
                    self.report_generator.export_to_excel(bill_data)
            else:
                print(bill_id)

# Main execution
if __name__ == "__main__":
    legiscan_key = 'REDACTED_LEGISCAN_KEY'
    openai_key = 'REDACTED_OPENAI_KEY'
    app = MainApplication(legiscan_key, openai_key)
    app.run()
