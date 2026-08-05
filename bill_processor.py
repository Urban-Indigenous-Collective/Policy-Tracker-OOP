import os
import re
import datetime
import traceback
import time
from typing import Callable, Optional

from bill_analyzer import BillAnalyzer
from document_text_store import get_document_text_store, infer_source_type
from legiscan_processor import LegiScanProcessor
from gov_processor import GovProcessor
from sponsor_utils import process_sponsors
from processing_log import log as plog, set_phase


class BillProcessor:
    def __init__(self, api_client, llm_provider, document_processor, indigenous_db, progress_callback=None):
        self.api_client = api_client
        self.llm_provider = llm_provider
        self.document_processor = document_processor
        self.indigenous_sponsors = ""
        self.indigenous_db = indigenous_db
        self.analyzer = BillAnalyzer(llm_provider)
        self.progress_callback = progress_callback
        self.legiscan_processor = LegiScanProcessor(indigenous_db, self.api_client)
        self.gov_processor = GovProcessor(document_processor, indigenous_db)
        self.compiled_bill = {}

    def _set_phase_progress(self, phase: str, fraction: float):
        if self.progress_callback:
            self.progress_callback(phase, fraction)

    def _retry_request(self, func, *args, **kwargs):
        max_retries = 7
        delay = 1
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_str = str(e).lower()
                if "rate limit" in error_str or "429" in error_str or "rate_limit_exceeded" in error_str:
                    print(
                        f"Rate limit error in {func.__name__}: {e}. "
                        f"Retrying in {delay}s (attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise e
        raise Exception(f"Max retries exceeded for {func.__name__}")

    def _seen_content_hash(self, url: str) -> str | None:
        db_path = os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
        try:
            from discovery.seen_store import SeenStore

            row = SeenStore(db_path).get(url)
            if row and row.get("content_hash"):
                return str(row["content_hash"])
        except Exception:
            pass
        return None

    def _apply_cached_doc_text(self, url: str, cached: dict) -> tuple[bool, str]:
        bill_id = cached.get("bill_id")
        doc_id = cached.get("doc_id")
        self.compiled_bill.update(
            {
                "decoded_text": cached["decoded_text"],
                "bill_id": bill_id,
                "doc_id": doc_id,
                "bill_text_url": url,
            }
        )
        self._set_phase_progress("fetch", 0.35)
        plog("Document text retrieved from cache")
        return True, "Document text retrieved from cache"

    def _write_doc_text_cache(
        self,
        url: str,
        decoded_text: str,
        *,
        bill_id=None,
        doc_id=None,
    ) -> None:
        store = get_document_text_store()
        if not store:
            return
        try:
            store.put(
                url,
                decoded_text,
                source_type=infer_source_type(url),
                bill_id=bill_id,
                doc_id=doc_id,
            )
        except Exception as exc:
            print(f"Warning: failed to write document text cache: {exc}")

    def get_doc_text(self, url, doc_id=None, bill_id=None, refresh=False):
        try:
            print(f"Getting document text from URL: {url}")
            store = get_document_text_store()
            if store and not refresh:
                cached = store.get(url)
                if cached and cached.get("decoded_text"):
                    seen_hash = self._seen_content_hash(url)
                    if seen_hash and seen_hash != cached.get("content_hash"):
                        print(
                            "Document text cache stale (SeenStore content_hash mismatch); re-fetching"
                        )
                    else:
                        print("Document text loaded from cache")
                        return self._apply_cached_doc_text(url, cached)

            plog(f"Fetching document text...")
            self._set_phase_progress("fetch", 0.1)
            set_phase("fetch", url[:80])
            if "legiscan.com" in url:
                print("URL identified as LegiScan URL.")
                decoded_text, bill_id, doc_id = self.legiscan_processor.get_legiscan_text(
                    url,
                    doc_id=doc_id,
                    bill_id=bill_id,
                    document_processor=self.document_processor,
                )
                if not bill_id:
                    error_msg = "Invalid or Unavailable LegiScan URL"
                    self.compiled_bill["error"] = error_msg
                    return False, error_msg

                self.compiled_bill.update(
                    {
                        "decoded_text": decoded_text,
                        "bill_id": bill_id,
                        "doc_id": doc_id,
                        "bill_text_url": url,
                    }
                )
                self._set_phase_progress("fetch", 0.35)
                plog("Document text retrieved")
                self._write_doc_text_cache(
                    url, decoded_text, bill_id=bill_id, doc_id=doc_id
                )
                return True, "LegiScan text retrieved successfully"

            if self.gov_processor.is_gov_url(url):
                print("URL identified as .gov URL.")
                decoded_text, error_msg = self.gov_processor.get_gov_document_text(url)
                if error_msg:
                    self.compiled_bill["error"] = error_msg
                    return False, error_msg

                self.compiled_bill.update(
                    {
                        "decoded_text": decoded_text,
                        "bill_id": None,
                        "doc_id": None,
                        "bill_text_url": url,
                    }
                )
                self._set_phase_progress("fetch", 0.35)
                self._write_doc_text_cache(url, decoded_text)
                return True, ".gov document text retrieved successfully"

            error_msg = "Unsupported URL format"
            self.compiled_bill["error"] = error_msg
            return False, error_msg

        except Exception as e:
            error_msg = f"Error retrieving document text: {str(e)}"
            self.compiled_bill["error"] = error_msg
            return False, error_msg

    def get_bill_details(self, bill_id):
        if not bill_id:
            print("No bill ID found, extracting metadata via structured LLM call")
            bill_link = self.compiled_bill.get("bill_text_url", "")
            bill_text = self.compiled_bill["decoded_text"]

            if ".gov" in bill_link:
                try:
                    self._set_phase_progress("metadata", 0.4)
                    metadata, warnings = self._retry_request(
                        self.analyzer.extract_gov_metadata, bill_text, bill_link
                    )
                    print(f"Metadata extracted: state={metadata.state}, title={metadata.title}")

                    processed_sponsors, processed_indigenous = process_sponsors(
                        metadata.sponsors_raw, self.indigenous_db
                    )

                    self.compiled_bill["bill"] = {
                        "state": metadata.state,
                        "title": metadata.title,
                        "bill_number": metadata.bill_number,
                        "session": {"session_title": metadata.session_title},
                        "status_date": metadata.last_updated,
                    }
                    self.compiled_bill.update(
                        {
                            "bill_sponsors": processed_sponsors,
                            "indigenous_sponsors": processed_indigenous,
                            "bill_passed_status": "Passed",
                            "progression_status": "Passed",
                            "chamber": metadata.chamber,
                            "chamber_details": metadata.chamber_details,
                            "validation_warnings": "; ".join(warnings) if warnings else "",
                        }
                    )
                    self.indigenous_sponsors = processed_indigenous
                    self._set_phase_progress("metadata", 0.45)
                    return True, "Gov metadata extracted successfully"

                except Exception as e:
                    error_msg = f"Error retrieving metadata via LLM: {str(e)}"
                    self.compiled_bill["error"] = error_msg
                    return False, error_msg

            self.compiled_bill["bill"] = {
                "state": "Not applicable",
                "title": "Unknown Title",
            }
            return True, "No bill ID provided; non-gov URL handled."

        try:
            self._set_phase_progress("metadata", 0.4)
            bill_details = self.api_client.get_bill_details(bill_id)
            bill = bill_details.get("bill", {})

            bill_sponsors = ", ".join(
                [
                    f"{s['role']} {s['name']} ({s['party']}) - District {s['district']}"
                    for s in bill.get("sponsors", [])
                ]
            )
            indigenous_sponsors = self.legiscan_processor.identify_indigenous_sponsors(bill_sponsors)
            if isinstance(indigenous_sponsors, list):
                indigenous_sponsors = ", ".join(indigenous_sponsors)
            plog(f"Metadata loaded: {bill.get('bill_number', 'unknown')}")

            self.compiled_bill.update(
                {
                    "bill_details": bill_details,
                    "bill": bill,
                    "indigenous_sponsors": indigenous_sponsors,
                    "bill_passed_status": self.legiscan_processor.check_bill_status(bill_details),
                    "chamber": self.legiscan_processor.get_chamber_details(bill),
                    "chamber_details": self.legiscan_processor.get_latest_action(bill),
                    "link": self.legiscan_processor.get_bill_link(bill),
                    "progression_status": self.legiscan_processor.status_codes.get(
                        bill.get("status"), "Unknown Status"
                    ),
                    "bill_sponsors": bill_sponsors,
                }
            )
            self.indigenous_sponsors = indigenous_sponsors
            self._set_phase_progress("metadata", 0.45)
            return True, "Bill details retrieved successfully"
        except Exception as e:
            error_msg = f"Error retrieving bill details: {str(e)}"
            self.compiled_bill["error"] = error_msg
            return False, error_msg

    def summarize_bill_text(self, cached_analysis: Optional[dict] = None):
        decoded_text = self.compiled_bill.get("decoded_text")
        if not decoded_text:
            error_msg = "No decoded text available for summarization."
            self.compiled_bill["error"] = error_msg
            return False, error_msg

        try:
            if cached_analysis:
                print("Using cached analysis result for duplicate URL")
                self.compiled_bill.update(cached_analysis)
            else:
                def phase_progress(phase, fraction):
                    if phase == "analysis":
                        self._set_phase_progress("analysis", fraction)
                    elif phase == "pros_cons":
                        self._set_phase_progress("pros_cons", fraction)

                fields = self._retry_request(
                    self.analyzer.run_full_analysis,
                    decoded_text,
                    self.indigenous_sponsors,
                    phase_progress,
                )
                self.compiled_bill.update(fields)

            if "error" in self.compiled_bill:
                del self.compiled_bill["error"]

            self._set_phase_progress("complete", 1.0)
            return True, "Bill text summarized successfully"

        except Exception as e:
            error_msg = f"ERROR during summarization: {str(e)}\n{traceback.format_exc()}"
            self.compiled_bill["error"] = error_msg
            print(error_msg)
            return False, error_msg

    def parse_bill_object(self):
        try:
            bill_info = self.compiled_bill
            bill = bill_info.get("bill") or {}

            bill_data = {
                "State": bill.get("state", "") or "Unknown",
                "Name": bill.get("title", "") or "Executive Order",
                "Bill Number": bill.get("bill_number", "") or "",
                "Status": bill_info.get("bill_passed_status", "Pending"),
                "Progression": bill_info.get("progression_status", "N/A"),
                "Chamber": bill_info.get("chamber", "Executive"),
                "Chamber Details": bill_info.get("chamber_details", ""),
                "Bill Overview (Link)": (
                    bill_info.get("link")
                    or bill_info.get("bill_text_url")
                    or ""
                ),
                "Bill Text": bill_info.get("bill_text_url", ""),
                "Optional Link": "",
                "Summary": bill_info.get("chat_summary", ""),
                "UIC Pros": bill_info.get("uic_pros", ""),
                "UIC Cons": bill_info.get("uic_cons", ""),
                "Mechanisms for Evaluation?": bill_info.get("mechanisms_eval", ""),
                "Mechanisms for Evaluation": bill_info.get("mechanisms_expl", ""),
                "Gender Inclusive Language?": bill_info.get("gender_inclusive_eval", ""),
                "Gender Inclusive Language": bill_info.get("gender_inclusive_expl", ""),
                "Prevention Efforts?": bill_info.get("prevention_efforts_eval", ""),
                "Prevention Efforts": bill_info.get("prevention_efforts_expl", ""),
                "Level of Survivor / Relative Input?": bill_info.get(
                    "survivor_relative_input_eval", ""
                ),
                "Level of Survivor / Relative Input": bill_info.get(
                    "survivor_relative_input_expl", ""
                ),
                "Centering of Indigenous Voices?": bill_info.get(
                    "centering_indigenous_voices_eval", ""
                ),
                "Centering of Indigenous Voices": bill_info.get(
                    "centering_indigenous_voices_expl", ""
                ),
                "Sponsors of the Legislation": self.compiled_bill.get(
                    "bill_sponsors", "Executive Order"
                ),
                "Indigenous Sponsorship": self.compiled_bill.get("indigenous_sponsors", ""),
                "Session": bill.get("session", {}).get("session_title", "N/A")
                if isinstance(bill.get("session"), dict)
                else bill.get("session", "N/A"),
                "Categories": bill_info.get("categories_eval", ""),
                "Last Update": (
                    bill.get("status_date")
                    or datetime.datetime.now().strftime("%Y-%m-%d")
                ),
                "Validation Warnings": bill_info.get("validation_warnings", ""),
            }

            self.compiled_bill["bill_data"] = bill_data
            return True, "Bill object parsed successfully"
        except Exception as e:
            error_msg = f"Error parsing bill object: {str(e)}"
            self.compiled_bill["error"] = error_msg
            return False, error_msg

    def process_bill(
        self,
        url,
        doc_id=None,
        cached_analysis: Optional[dict] = None,
        refresh: bool = False,
    ):
        success, message = self.get_doc_text(url, doc_id=doc_id, refresh=refresh)
        if not success:
            return False, message

        bill_id = self.compiled_bill.get("bill_id")
        success, message = self.get_bill_details(bill_id)
        if not success:
            return False, message

        success, message = self.summarize_bill_text(cached_analysis=cached_analysis)
        if not success:
            return False, message

        success, message = self.parse_bill_object()
        if not success:
            return False, message

        print("Processing completed successfully.")
        return True, "Processing completed successfully"

    def get_analysis_cache_payload(self) -> dict:
        keys = [
            "chat_summary",
            "gender_inclusive_eval",
            "gender_inclusive_expl",
            "mechanisms_eval",
            "mechanisms_expl",
            "prevention_efforts_eval",
            "prevention_efforts_expl",
            "centering_indigenous_voices_eval",
            "centering_indigenous_voices_expl",
            "survivor_relative_input_eval",
            "survivor_relative_input_expl",
            "categories_eval",
            "uic_pros",
            "uic_cons",
            "validation_warnings",
        ]
        return {k: self.compiled_bill.get(k) for k in keys if k in self.compiled_bill}
