"""The discovery pipeline must fail crawled candidates closed at three points."""

import pytest

from discovery.models import Candidate
from discovery.pipeline import DiscoveryPipeline, DiscoveryRunStats
from discovery.seen_store import SeenStore

MMIP_PAGE_TEXT = (
    "Montana Missing and Murdered Indigenous Persons Advisory Council. The council "
    "works to reduce the number of missing Indigenous persons in Montana, improve "
    "collaboration among tribal, state and federal law enforcement, and track data "
    "on missing and murdered Indigenous people across the state. "
) * 6

IOWA_SEARCH_SHELL = (
    "Search results for tribal missing persons | Search | Iowa.gov Skip to main "
    "content Official State of Iowa Website Agencies A-Z Programs & Services"
)


class StubFetcher:
    def __init__(self, text=""):
        self.text = text
        self.urls = []

    def discover(self):
        return []

    def fetch_page_text(self, url):
        self.urls.append(url)
        return self.text, "hash-1"


class StubRelevanceGate:
    def __init__(self):
        self.evaluations = 0

    def prescreen(self, candidate, excerpt=""):
        return True

    def evaluate(self, candidate, excerpt="", prescreened=False):
        self.evaluations += 1
        return True, _RelevanceResult(), "llm"


class _RelevanceResult:
    confidence = 0.95
    rationale = "Mentions missing and murdered Indigenous persons."


class StubDuplicateIndex:
    def is_duplicate(self, *args, **kwargs):
        return False

    def register(self, *args, **kwargs):
        pass


class StubAirtable:
    def __init__(self):
        self.created = []

    def create_pending_record(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "recStub"}


class StubBillProcessor:
    """Stands in for the LLM-driven .gov metadata path."""

    def __init__(self, decoded_text, bill_data):
        self.compiled_bill = {}
        self._decoded_text = decoded_text
        self._bill_data = bill_data

    def get_doc_text(self, url, bill_id=None):
        self.compiled_bill["decoded_text"] = self._decoded_text
        self.compiled_bill["bill_id"] = None
        return True, "ok"

    def get_bill_details(self, bill_id):
        return True, "ok"

    def summarize_bill_text(self):
        return True, "ok"

    def parse_bill_object(self):
        self.compiled_bill["bill_data"] = dict(self._bill_data)
        return True, "ok"


class StubMainApp:
    def __init__(self, bill_processor=None, legiscan_processor=None):
        self.airtable_client = StubAirtable()
        self.llm_provider = None
        self.api_client = None
        self.bill_processor = bill_processor
        self.legiscan_processor = legiscan_processor


class StubLegiscanProcessor:
    def __init__(self, excerpt=""):
        self.excerpt = excerpt
        self.calls = []

    def get_bill_excerpt_for_relevance(self, url, bill_id=None, document_processor=None, max_chars=12000):
        self.calls.append((url, bill_id))
        return self.excerpt


def build_pipeline(tmp_path, page_text="", bill_processor=None, legiscan_excerpt=MMIP_PAGE_TEXT):
    main_app = StubMainApp(
        bill_processor,
        legiscan_processor=StubLegiscanProcessor(legiscan_excerpt),
    )
    pipeline = DiscoveryPipeline(
        main_app=main_app,
        seen_store=SeenStore(str(tmp_path / "seen.db")),
        airtable=main_app.airtable_client,
        slack=object(),
        relevance_gate=StubRelevanceGate(),
        legiscan_source=StubFetcher(),
        state_source=StubFetcher(page_text),
        federal_source=StubFetcher(page_text),
    )
    pipeline.duplicate_index = StubDuplicateIndex()
    return pipeline


def candidate(url, title="Tribal missing persons", source="state_site"):
    return Candidate(source=source, state="IA", url=url, title=title, snippet=title)


class TestUrlShapeGate:
    def test_search_url_rejected_before_any_fetch(self, tmp_path):
        pipeline = build_pipeline(tmp_path, MMIP_PAGE_TEXT)
        stats = DiscoveryRunStats()
        url = "https://www.iowa.gov/search?q=tribal%20missing%20persons"

        pipeline._process_candidate(candidate(url), stats)

        assert stats.rejected == 1
        assert stats.analyzed == 0
        assert pipeline.state_source.urls == []
        assert pipeline.relevance_gate.evaluations == 0

    def test_legiscan_candidates_skip_url_shape_gate(self, tmp_path):
        pipeline = build_pipeline(tmp_path, MMIP_PAGE_TEXT)
        stats = DiscoveryRunStats()
        url = "https://legiscan.com/IA/bill/HF2521/2024?q=missing"

        pipeline._process_candidate(candidate(url, source="legiscan"), stats)

        assert stats.rejected == 0
        assert pipeline.relevance_gate.evaluations == 1
        assert pipeline.main_app.legiscan_processor.calls

    def test_legiscan_without_mmip_bill_text_rejected_before_llm(self, tmp_path):
        generic_bill = (
            "AN ACT relating to the state budget for fiscal year 2027. "
            "Appropriates funds for general government operations. "
            "This bill allocates revenue to agencies and departments statewide. "
        ) * 3
        pipeline = build_pipeline(tmp_path, legiscan_excerpt=generic_bill)
        stats = DiscoveryRunStats()
        url = "https://legiscan.com/VA/bill/HB30/2026"

        pipeline._process_candidate(
            candidate(url, title="Budget Bill.", source="legiscan"),
            stats,
        )

        assert stats.rejected == 1
        assert pipeline.relevance_gate.evaluations == 0


class TestDocumentGate:
    def test_search_shell_rejected_before_llm(self, tmp_path):
        pipeline = build_pipeline(tmp_path, IOWA_SEARCH_SHELL)
        stats = DiscoveryRunStats()

        pipeline._process_candidate(candidate("https://www.iowa.gov/federal-assistance-0"), stats)

        assert stats.rejected == 1
        assert pipeline.relevance_gate.evaluations == 0

    def test_real_document_reaches_the_llm_gate(self, tmp_path):
        processor = StubBillProcessor(
            MMIP_PAGE_TEXT,
            {
                "State": "MT",
                "Name": "Montana Missing and Murdered Indigenous Persons Advisory Council",
                "Bill Number": "",
                "Last Update": "2026-04-28",
                "Bill Text": "https://dojmt.gov/mmip-home/",
                "Bill Overview (Link)": "https://dojmt.gov/mmip-home/",
                "Validation Warnings": "",
            },
        )
        pipeline = build_pipeline(tmp_path, MMIP_PAGE_TEXT, processor)
        stats = DiscoveryRunStats()

        pipeline._process_candidate(candidate("https://dojmt.gov/mmip-home/"), stats)

        assert pipeline.relevance_gate.evaluations == 1
        assert stats.analyzed == 1
        assert len(pipeline.airtable.created) == 1


class TestConsistencyGate:
    def _pipeline_with_record(self, tmp_path, bill_data, decoded_text=MMIP_PAGE_TEXT):
        processor = StubBillProcessor(decoded_text, bill_data)
        return build_pipeline(tmp_path, MMIP_PAGE_TEXT, processor)

    def test_title_absent_from_document_blocks_the_write(self, tmp_path):
        pipeline = self._pipeline_with_record(
            tmp_path,
            {
                "State": "IA",
                "Name": "Red Tape Review Rule Report",
                "Bill Number": "",
                "Last Update": "2023-08-31",
                "Bill Text": "https://www.iowa.gov/media/133/download",
                "Bill Overview (Link)": "https://www.iowa.gov/media/133/download",
                "Validation Warnings": "",
            },
        )
        stats = DiscoveryRunStats()

        pipeline._process_candidate(candidate("https://www.iowa.gov/media/133/download"), stats)

        assert stats.analyzed == 0
        assert stats.rejected == 1
        assert pipeline.airtable.created == []

    def test_hallucinated_bill_number_is_cleared_and_warned(self, tmp_path):
        pipeline = self._pipeline_with_record(
            tmp_path,
            {
                "State": "MT",
                "Name": "Montana Missing and Murdered Indigenous Persons Advisory Council",
                "Bill Number": "EO14053",
                "Last Update": "2026-01-01",
                "Bill Text": "https://dojmt.gov/mmip-home/",
                "Bill Overview (Link)": "https://dojmt.gov/mmip-home/",
                "Validation Warnings": "",
            },
        )
        stats = DiscoveryRunStats()

        pipeline._process_candidate(candidate("https://dojmt.gov/mmip-home/"), stats)

        assert stats.analyzed == 1
        written = pipeline.airtable.created[0]["bill_data"]
        assert written["Bill Number"] == ""
        assert "EO14053" in written["Validation Warnings"]
        assert "Last Update" in written["Validation Warnings"]
