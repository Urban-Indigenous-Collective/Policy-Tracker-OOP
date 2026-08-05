import datetime
import re
import requests

TRACKED_STATUS_FIELD_NAMES = (
    "Status",
    "Progression",
    "Chamber",
    "Chamber Details",
    "Last Update",
)

_BILL_URL_RE = re.compile(
    r"legiscan\.com/([A-Z]{2})/(?:bill|text)/([A-Z]+[0-9]+)/([0-9]{4})",
    re.IGNORECASE,
)
_FAILED_ACTION_RE = re.compile(r"failed to adopt|failed passage|died in|withdrawn", re.I)


def normalize_bill_number(bill_number: str) -> str:
    """Normalize bill numbers for identity comparison (HB0015 -> HB15)."""
    compact = re.sub(r"[^A-Z0-9]", "", str(bill_number or "").upper())
    match = re.match(r"^([A-Z]+)0*(\d+)$", compact)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return compact


def parse_legiscan_bill_url(url: str) -> tuple[str, str, int] | None:
    match = _BILL_URL_RE.search(url or "")
    if not match:
        return None
    return match.group(1).upper(), match.group(2).upper(), int(match.group(3))


class LegiScanProcessor:

    def __init__(self, indigenous_db, api_client):
        self.indigenous_db = indigenous_db
        self.api_client = api_client

        self.status_codes = {
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
        self.chamber_full_names = {
            'A': 'House',  # Assembly is standardized to House
            'S': 'Senate',
            'H': 'House',  # Handle 'H' as House
            'L': 'Legislative Body',  # Potentially for unicameral legislature
            'N/A': 'Not Available'  # Handle cases where chamber info is missing
        }

    def extract_doc_id(self, url):
        """
        Extracts doc ID from a given URL.
        """
        print(f"Extracting bill ID from URL: {url}")
        match = re.search(r'/id/(\d+)', url)
        if match:
            print(f"Found bill ID: {match.group(1)}")
            return match.group(1)
        else:
            print("No bill ID found in URL.")
            return None
            
    def is_legiscan_url(self, url):
        """
        Checks if the URL is a LegiScan link.
        """
        return "legiscan.com" in url

    def _get_session_list(self, state_code: str) -> list[dict]:
        getter = getattr(self.api_client, "get_session_list", None)
        if callable(getter):
            payload = getter(state_code) or {}
            return payload.get("sessions") or []
        api_key = self.api_client.get_api_key()
        response = requests.get(
            f"https://api.legiscan.com/?key={api_key}&op=getSessionList&state={state_code}",
            timeout=60,
        )
        if response.status_code != 200:
            return []
        return response.json().get("sessions") or []

    def _get_master_list(self, session_id: int | str) -> dict:
        getter = getattr(self.api_client, "get_master_list", None)
        if callable(getter):
            payload = getter(session_id) or {}
            return payload.get("masterlist") or {}
        api_key = self.api_client.get_api_key()
        response = requests.get(
            f"https://api.legiscan.com/?key={api_key}&op=getMasterList&id={session_id}",
            timeout=60,
        )
        if response.status_code != 200:
            return {}
        return response.json().get("masterlist") or {}

    def get_latest_bill_id(self, state_code, session_year, bill_number):
        """Fetch bill_id for state/year/bill_number, trying all matching sessions."""
        target = normalize_bill_number(bill_number)
        sessions = self._get_session_list(state_code)
        matching_sessions = [
            session
            for session in sessions
            if session.get("year_start", 0) <= session_year <= session.get("year_end", 0)
        ]
        for session in matching_sessions:
            master_list = self._get_master_list(session["session_id"])
            for bill_data in master_list.values():
                if not isinstance(bill_data, dict):
                    continue
                if normalize_bill_number(bill_data.get("number", "")) == target:
                    bill_id = bill_data["bill_id"]
                    return int(bill_id) if str(bill_id).isdigit() else bill_id
        return None

    def search_bill_id(self, state: str, bill_number: str, year: int) -> str | None:
        target = normalize_bill_number(bill_number)
        data = self.api_client.get_search_raw(bill_number, state=state, year=year)
        if not data or data.get("status") != "OK":
            return None
        results = data.get("searchresult") or {}
        for key, item in results.items():
            if key == "summary" or not isinstance(item, dict):
                continue
            if normalize_bill_number(item.get("bill_number", "")) == target:
                bill_id = item.get("bill_id")
                return str(bill_id) if bill_id is not None else None
        return None

    def resolve_bill_id(
        self,
        url: str,
        *,
        state: str = "",
        bill_number: str = "",
        year: int | None = None,
    ) -> str | None:
        """Resolve a LegiScan bill_id from overview/text URLs and optional hints."""
        if not url or not self.is_legiscan_url(url):
            if state and bill_number and year:
                return self.search_bill_id(state, bill_number, year) or self.get_latest_bill_id(
                    state, year, bill_number
                )
            return None

        doc_id = self.extract_doc_id(url)
        if doc_id and "/text/" in url:
            text_getter = getattr(self.api_client, "get_bill_text_doc", None)
            if callable(text_getter):
                text_doc = text_getter(doc_id) or {}
            else:
                text_doc = self.api_client.get_bill_text(doc_id) or {}
            bill_id = text_doc.get("bill_id")
            if bill_id:
                return str(bill_id)

        parsed = parse_legiscan_bill_url(url)
        if parsed:
            state_code, parsed_bill, session_year = parsed
            found = self.get_latest_bill_id(state_code, session_year, parsed_bill)
            if found:
                return str(found)
            found = self.search_bill_id(state_code, parsed_bill, session_year)
            if found:
                return found

        if state and bill_number and year:
            found = self.search_bill_id(state, bill_number, year)
            if found:
                return found
            found = self.get_latest_bill_id(state, year, bill_number)
            return str(found) if found else None
        return None

    def extract_status_fields(self, bill_details: dict) -> dict[str, str]:
        bill = bill_details.get("bill") or {}
        return {
            "Status": self.check_bill_status(bill_details),
            "Progression": self.status_codes.get(bill.get("status"), "Unknown Status"),
            "Chamber": self.get_chamber_details(bill),
            "Chamber Details": self.get_latest_action(bill),
            "Last Update": str(bill.get("status_date") or ""),
        }

    def extract_metadata_fields(self, bill_details: dict) -> dict[str, str]:
        """Authoritative LegiScan session/date metadata for backfill."""
        bill = bill_details.get("bill") or {}
        session = bill.get("session") or {}
        session_title = ""
        if isinstance(session, dict):
            session_title = str(session.get("session_title") or "").strip()
        elif session:
            session_title = str(session).strip()
        fields = self.extract_status_fields(bill_details)
        if session_title:
            fields["Session"] = session_title
        return fields

    def process_legiscan_url(self, url):
        """Legacy helper; prefer resolve_bill_id."""
        return self.resolve_bill_id(url)


    def identify_indigenous_sponsors(self, sponsors):
        """
        Identifies and returns a list of Indigenous sponsors from the given list of sponsors.
        """
        sponsors = [name.strip() for name in sponsors.split(',')]
        indigenous_sponsors = []

        for sponsor in sponsors:
            if self.indigenous_db.is_indigenous_sponsor(sponsor):
                indigenous_sponsors.append(sponsor)

        return ", ".join(indigenous_sponsors)

    def check_bill_status(self, bill_details):
        """Checks the status of a bill."""
        bill = bill_details.get("bill") or {}
        history = bill.get("history") or []
        if history:
            last_action = str(history[-1].get("action") or "")
            if _FAILED_ACTION_RE.search(last_action):
                return "Failed"

        status_code = bill.get("status")
        if bill.get("completed") == 1:
            if status_code == 6:
                return "Failed"
            if history and _FAILED_ACTION_RE.search(str(history[-1].get("action") or "")):
                return "Failed"
            return "Passed"

        session = bill.get("session") or {}
        session_end_year = session.get("year_end") if isinstance(session, dict) else None
        if session_end_year:
            session_end_date = datetime.date(int(session_end_year), 12, 31)
            if datetime.date.today() > session_end_date:
                return "Failed"
        return "Pending"

    def get_chamber_details(self, bill):
        """
        Extracts the chamber details (full name of the chamber) from a bill.
        """
        current_body_short = bill.get('body', 'N/A')
        chamber = self.chamber_full_names.get(current_body_short, 'Unknown')
        return chamber

    def get_latest_action(self, bill):
        """
        Extracts the latest action details from a bill.
        """
        history = bill.get('history', [])
        if history:
            latest_action = history[-1]  # Get the most recent action
            action_text = latest_action.get('action', 'N/A')
            action_chamber = latest_action.get('chamber', 'N/A')
            action_date = latest_action.get('date', 'N/A')
            chamber_details = f"{action_date} - {action_chamber}: {action_text}"
        else:
            chamber_details = 'N/A'
        
        return chamber_details

    def get_bill_link(self, bill):
        """
        Extracts the URL link of the bill.
        """
        return bill.get('url', 'N/A')

    def get_bill_id_and_text(self, bill_id, doc_id=None, document_processor=None):
        """
        Fetches the bill text data using the bill ID and stores the document ID.
        If a document ID is provided, it uses that instead.
        """
        if doc_id:
            print(f"Using provided document ID: {doc_id}")
        else:
            bill_details = self.api_client.get_bill_details(bill_id)

            if not bill_details or 'bill' not in bill_details or 'texts' not in bill_details['bill']:
                print("Error: Bill text data not available or no documents found.")
                return "Error: Bill text data not available", None

            last_doc = bill_details['bill']['texts'][-1]
            doc_id = last_doc.get('doc_id')
            print(f"Retrieved document ID from bill details: {doc_id}")

        print(f"Getting text with doc id: {doc_id}")
        bill_text_data = self.api_client.get_bill_text(doc_id)

        if not bill_text_data or 'doc' not in bill_text_data:
            print("Error: Bill text data not available or document missing.")
            return "Error: Bill text data not available", None

        mime_type = bill_text_data.get("mime")
        print(f"MIME type of the document: {mime_type}")

        if mime_type == "text/html":
            html_text = document_processor.decode_base64(bill_text_data["doc"])
            decoded_text = html_text.decode('latin-1')
            decoded_text = document_processor.strip_html_tags(decoded_text)
            return decoded_text, doc_id

        elif mime_type == "application/pdf":
            pdf_data = document_processor.decode_base64(bill_text_data['doc'])
            decoded_text = document_processor.extract_text_from_pdf(pdf_data)
            return decoded_text, doc_id

        else:
            print("Error: Document format not supported or missing.")
            return "Error: Document format not supported or missing", None


    def get_legiscan_text(self, legiscan_url, doc_id=None, document_processor=None):
        """
        Retrieves the bill text from LegiScan using either a provided doc_id or by processing the URL to get the bill ID.
        """
        # Use the provided doc_id if available
        print(f"Retrieved doc ID: {doc_id}")
        bill_id = None

        if doc_id:
            # Get bill text details using the doc_id
            bill_text_details = self.api_client.get_bill_text(doc_id)
            bill_id = bill_text_details.get('bill_id')
            print(f"Bill ID retrieved from bill text details: {bill_id}")
            if not bill_id:
                return "Invalid or Unavailable LegiScan URL", None, None
        else:
            # Retrieve bill_id from the URL
            bill_id = self.process_legiscan_url(legiscan_url)
            print(f"Bill ID returned from initial fetch: {bill_id}")
            if not bill_id:
                return "Invalid or Unavailable LegiScan URL", None, None

        # Retrieve the bill text using the provided doc_id or fetch the doc_id and get the text
        decoded_text, doc_id = self.get_bill_id_and_text(
            bill_id, doc_id=doc_id, document_processor=document_processor)
        
        return decoded_text, bill_id, doc_id