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
from legiscan_processor import LegiScanProcessor

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

        self.legiscan_processor = LegiScanProcessor(self.indigenous_db, self.api_client)




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
            # Log URL processing
            print(f"Processing URL: {url}")

            # Step 1: Check if the URL has a doc ID using LegiScan processing functions
            doc_id = self.legiscan_processor.extract_doc_id(url)  # Assuming extract_doc_id method exists

            # Step 2: If a doc ID is found, fetch the full bill URL
            if doc_id:
                # Get bill text details using the extracted doc ID
                bill_text_details = self.api_client.get_bill_text(doc_id)
                extracted_bill_id = bill_text_details.get('bill_id')

                print(f"Extracted bill ID: {extracted_bill_id}")
                print(f"Extracted text field: {bill_text_details.get('state_link')}")

                if extracted_bill_id:
                    # Fetch bill details using the extracted bill_id
                    bill_details = self.api_client.get_bill_details(extracted_bill_id)
                    full_url = bill_details.get('bill', {}).get('url')
                    print(f"Bill ID found: {extracted_bill_id}. Full URL obtained: {full_url}")
                else:
                    # If no bill_id is found in the bill text details, fallback to the original URL
                    print(f"No valid bill ID found in bill text details. Using original URL.")
                    full_url = url
            else:
                # If no doc ID is found, use the original URL as the full URL
                full_url = url
                print(f"No doc ID found in URL. Using original URL: {full_url}")
                doc_id = None  # Ensure doc_id is None when not found

            # Step 3: Check if the full URL is already in Airtable in the Bill Overview (Link) category
            is_duplicate, record_data = self.airtable_client.check_url_in_airtable(full_url, category="Bill Overview (Link)")

            if is_duplicate:
                # Log the duplicate detection
                print(f"Duplicate found for URL: {full_url}")

                # Mark as duplicate and skip
                state = record_data.get('State', 'Unknown')
                title = record_data.get('Name', 'Unknown')
                bill_number = record_data.get('Bill Number', 'Unknown')
                bill_text_url = record_data.get('Bill Text', 'Unknown')

                processed_data.append({
                    'State': state,
                    'Title': title,
                    'Bill Number': bill_number,
                    'Status': 'Duplicate -- Skipped',
                    'Bill Text': bill_text_url,
                })
            else:
                result = self.process_single_url(full_url, doc_id=doc_id)
                # Whether it's successful data or an error message, append it to processed_data
                processed_data.append(result)

            # Update and print progress
            self.progress = (i + 1) / total_urls * 100
            print(f"Processed URL {i + 1}/{total_urls}. Current progress: {self.progress}%")
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

    def process_single_url(self, url, doc_id=None):
        try:
            print("Processing single URL!")
            # Call summarize_bill_text, which now stores data in compiled_bill
            self.bill_processor.summarize_bill_text(url, doc_id=doc_id)
            bill_id = self.bill_processor.compiled_bill.get('bill_id')
            print(f"Bill ID returned from summarize_bill text: {bill_id}")

            # Proceed if bill_id is valid
            if isinstance(bill_id, int):
                print(f"Bill ID before final parsing bill object: {bill_id}")

                # Ensure the compiled_bill includes necessary data
                if 'bill' in self.bill_processor.compiled_bill:
                    # Call parse_bill_object with no arguments
                    bill_data = self.bill_processor.parse_bill_object()
                    return bill_data
                else:
                    return {'url': url, 'error': "Bill data missing in compiled_bill."}
            else:
                print(bill_id)
                return {'url': url, 'error': f"Invalid bill ID: {bill_id}"}

        except Exception as e:
            # Handle any exception
            print(f"Error processing URL {url}: {e}")
            return {'url': url, 'error': f"Error processing URL: {str(e)}"}

# Main execution
if __name__ == "__main__":
    legiscan_key = 'REDACTED_LEGISCAN_KEY'
    openai_key = 'REDACTED_OPENAI_KEY'
    app = MainApplication(legiscan_key, openai_key)
    app.run()
