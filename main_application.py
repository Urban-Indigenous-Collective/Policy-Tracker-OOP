import logging
import re
import time

from api_client import APIClient
from bill_processor import BillProcessor
from document_processor import DocumentProcessor
from report_generator import ReportGenerator
from llm.factory import get_llm_provider
from airtable_client import AirtableClient
from wikipedia_api_client import WikipediaAPIClient
from indigenous_database import IndigenousDatabase
from legiscan_processor import LegiScanProcessor
from processing_log import log as plog, reset as plog_reset, set_phase

logger = logging.getLogger(__name__)


class MainApplication:
    def __init__(self, legiscan_key):
        self.api_client = APIClient(legiscan_key)
        self.llm_provider = get_llm_provider()
        self.airtable_client = AirtableClient()
        self.document_processor = DocumentProcessor(self.llm_provider)
        self.report_generator = ReportGenerator()
        self.wikipedia_client = WikipediaAPIClient()
        self.indigenous_db = IndigenousDatabase()
        print("Building Indigenous database...")
        self.indigenous_db.build_database()

        self._url_progress_base = 0.0
        self._url_progress_span = 100.0
        self.progress = 0
        self.current_phase = "Idle"
        self.current_detail = ""
        self.bill_processor = None
        self._init_bill_processor()

        self.legiscan_processor = LegiScanProcessor(self.indigenous_db, self.api_client)

    def _init_bill_processor(self):
        self.bill_processor = BillProcessor(
            self.api_client,
            self.llm_provider,
            self.document_processor,
            self.indigenous_db,
            progress_callback=self._on_bill_phase_progress,
        )

    def _on_bill_phase_progress(self, phase, fraction):
        phase_weights = {
            "fetch": (0.0, 0.35),
            "metadata": (0.35, 0.45),
            "analysis": (0.45, 0.75),
            "pros_cons": (0.75, 0.95),
            "complete": (0.95, 1.0),
        }
        start, end = phase_weights.get(phase, (0.0, 1.0))
        inner = start + (end - start) * min(max(fraction, 0.0), 1.0)
        self.progress = self._url_progress_base + inner * self._url_progress_span
        self.current_phase = phase
        pct = int(inner * 100)
        self.current_detail = f"{pct}%"
        set_phase(phase, self.current_detail)
        logger.info(
            "progress phase=%s fraction=%.2f overall=%.1f",
            phase,
            fraction,
            self.progress,
        )

    def resolve_canonical_url(self, url):
        doc_id = self.legiscan_processor.extract_doc_id(url)
        if doc_id:
            bill_text_details = self.api_client.get_bill_text(doc_id)
            extracted_bill_id = bill_text_details.get("bill_id")
            if extracted_bill_id:
                bill_details = self.api_client.get_bill_details(extracted_bill_id)
                full_url = bill_details.get("bill", {}).get("url")
                if full_url:
                    return full_url, doc_id
        return url, doc_id

    def process_urls_for_web(self, urls_string):
        urls_string = urls_string.strip()
        raw_urls = [u.strip() for u in re.split(r"[,\s]+", urls_string) if u.strip()]

        url_regex = re.compile(
            r"^(http|https)://"
            r"([A-Za-z0-9-]+\.)+[A-Za-z]{2,6}"
            r"(:[0-9]{1,5})?"
            r"(/.*)?$"
        )
        valid_urls = [u for u in raw_urls if url_regex.match(u)]
        invalid_urls = [u for u in raw_urls if u not in valid_urls]
        if invalid_urls:
            print(f"Invalid URLs skipped: {invalid_urls}")

        resolved = []
        for url in valid_urls:
            canonical, doc_id = self.resolve_canonical_url(url)
            resolved.append((url, canonical, doc_id))

        total_urls = len(resolved)
        print(f"Starting URL processing. Total URLs: {total_urls}")
        self.progress = 0
        processed_data = []

        # Disable caches so repeated links get independent LLM runs (comparison testing).
        prior_cache_setting = self.bill_processor.analyzer.cache_enabled
        self.bill_processor.analyzer.cache_enabled = False

        for i, (original_url, full_url, doc_id) in enumerate(resolved):
            print(f"Processing URL: {original_url} (canonical: {full_url})")
            plog(f"Bill {i + 1}/{total_urls}: {full_url}")
            set_phase("batch", f"bill {i + 1} of {total_urls}")
            span = 100.0 / total_urls if total_urls else 100.0
            self._url_progress_base = i * span
            self._url_progress_span = span

            is_duplicate, record_data = self.airtable_client.check_url_in_airtable(
                full_url, category="Bill Overview (Link)"
            )

            if is_duplicate:
                processed_data.append(
                    {
                        "State": record_data.get("State", "Unknown"),
                        "Title": record_data.get("Name", "Unknown"),
                        "Bill Number": record_data.get("Bill Number", "Unknown"),
                        "Status": "Duplicate -- Skipped",
                        "Bill Text": record_data.get("Bill Text", "Unknown"),
                    }
                )
            else:
                result = self.process_single_url(full_url, doc_id=doc_id)
                processed_data.append(result)

            self.progress = (i + 1) / total_urls * 100
            plog(f"Finished bill {i + 1}/{total_urls} ({self.progress:.0f}%)")
            print(f"Processed URL {i + 1}/{total_urls}. Current progress: {self.progress}%")
            time.sleep(0.2)

        self.bill_processor.analyzer.cache_enabled = prior_cache_setting

        if processed_data:
            excel_file_path = self.report_generator.export_to_excel(processed_data)
            print(excel_file_path)
            return excel_file_path
        return None

    def get_progress(self):
        return self.progress

    def get_status_detail(self):
        return {
            "phase": self.current_phase,
            "detail": self.current_detail,
        }

    def process_single_url(self, url, doc_id=None, cached_analysis=None):
        try:
            self.bill_processor.compiled_bill = {}
            success, message = self.bill_processor.process_bill(
                url, doc_id=doc_id, cached_analysis=cached_analysis
            )
            if success:
                return self.bill_processor.compiled_bill.get("bill_data")
            error_msg = self.bill_processor.compiled_bill.get("error", "Unknown error")
            return {"url": url, "error": error_msg}
        except Exception as e:
            return {"url": url, "error": f"Error processing URL: {str(e)}"}

    def check_politician_indigenous_status(self, politicians_list):
        if not self.indigenous_db.database:
            self.indigenous_db.build_database()
        return {
            politician: self.indigenous_db.is_indigenous_sponsor(politician)
            for politician in politicians_list
        }

    def run(self):
        print("Choose an option:")
        print("1 - Process LegiScan URLs")
        choice = input("Enter choice: ").strip()
        if choice == "1":
            urls = []
            print("Enter LegiScan URLs (type 'exit' to finish):")
            while True:
                url = input("Enter URL: ")
                if url.lower() == "exit":
                    break
                urls.append(url)
            self.process_urls_for_web(",".join(urls))


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    app = MainApplication(os.getenv("LEGISCAN_KEY"))
    app.run()
