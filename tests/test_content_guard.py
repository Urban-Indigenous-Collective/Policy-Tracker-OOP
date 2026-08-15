"""Guards for non-LegiScan candidates, exercised against the 2026-08-02 junk batch."""

import pytest

from content_guard import (
    DEFAULT_MIN_DOC_CHARS,
    bill_number_in_text,
    check_document_text,
    check_record_consistency,
    check_url_shape,
    merge_warnings,
    screen_candidate_document,
    title_overlap,
)

MMIP_DOC = (
    "Governor Stein Proclaims May 5 as Day of Awareness for Missing and Murdered "
    "Indigenous Women. The proclamation recognizes that American Indian and Alaska "
    "Native women experience violence at disproportionate rates, and directs the "
    "Commission of Indian Affairs to expand support for families of missing "
    "Indigenous relatives across the state's eight recognized tribes. "
) * 6


class TestUrlShape:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.iowa.gov/search?q=tribal%20missing%20persons",
            "https://www.iowa.gov/bs/search?q=tribal%20missing%20persons",
            "https://leginfo.legislature.ca.gov/faces/billSearchClient.xhtml",
            "https://example.gov/results?query=mmip",
            "https://example.gov/pages/search",
        ],
    )
    def test_rejects_search_urls(self, url):
        verdict = check_url_shape(url)
        assert not verdict
        assert verdict.code == "url_search_page"

    @pytest.mark.parametrize(
        "url",
        ["https://example.gov/index.php", "https://example.gov/", "https://example.gov/home"],
    )
    def test_rejects_nav_index_urls(self, url):
        assert check_url_shape(url).code == "url_nav_index"

    @pytest.mark.parametrize(
        "url,code",
        [
            ("javascript:void(0)", "url_not_http"),
            ("mailto:clerk@example.gov", "url_not_http"),
            ("", "url_empty"),
            ("https:///no-host", "url_no_host"),
        ],
    )
    def test_rejects_non_document_urls(self, url, code):
        assert check_url_shape(url).code == code

    @pytest.mark.parametrize(
        "url",
        [
            "https://dojmt.gov/mmip-home/",
            "https://www.doa.nc.gov/news/press-releases/2026/05/05/governor-stein-proclaims-may-5-day-awareness-missing-and-murdered-indigenous-women",
            "https://www.federalregister.gov/documents/2024/05/13/2024-10533/missing-or-murdered-indigenous-persons-awareness-day-2024",
            "https://example.gov/research-report-2024.pdf",
        ],
    )
    def test_allows_real_documents(self, url):
        assert check_url_shape(url)

    def test_blank_query_value_is_not_a_search_page(self):
        assert check_url_shape("https://example.gov/bills/hb1234?q=")


class TestDocumentText:
    def test_rejects_empty_text(self):
        assert check_document_text("", "https://app.leg.wa.gov/billinfo/prefiled").code == "doc_empty"

    def test_rejects_whitespace_only_text(self):
        assert check_document_text("   \n\t  ").code == "doc_empty"

    def test_rejects_short_pdf_wrapper(self):
        wrapper = (
            "Justice for Renee Nicole Good | MELT Act, RADAR Act, NY4ALL Skip to main content "
            "January 12, 2026 If the PDF is not displaying properly, download the PDF."
        )
        verdict = check_document_text(wrapper)
        assert verdict.code == "doc_too_short"
        assert str(DEFAULT_MIN_DOC_CHARS) in verdict.detail

    @pytest.mark.parametrize(
        "head",
        [
            "Search results for tribal missing persons | Search | Iowa.gov",
            "Rezultati pretrage za tribal missing persons | Pretraga | Iowa.gov",
            "No results found for your query",
        ],
    )
    def test_rejects_search_result_pages(self, head):
        assert check_document_text(head + " " + MMIP_DOC).code == "doc_search_results"

    def test_search_marker_deep_in_a_real_document_is_ignored(self):
        text = MMIP_DOC + " Use the portal to view search results for case records."
        assert check_document_text(text)

    def test_rejects_long_document_without_mmip_terms(self):
        report = (
            "Red Tape Review Rule Report for the Iowa Department of Insurance and Financial "
            "Services proposing amendments to Chapter 181 regarding organization and operation. "
        ) * 20
        assert check_document_text(report).code == "doc_no_mmip_evidence"

    def test_allows_real_mmip_document(self):
        assert check_document_text(MMIP_DOC, "https://www.doa.nc.gov/news/press-releases/x")

    def test_min_length_is_configurable(self, monkeypatch):
        monkeypatch.setenv("DISCOVERY_MIN_DOC_CHARS", "50000")
        assert check_document_text(MMIP_DOC).code == "doc_too_short"

    def test_allows_short_federal_register_proclamation_with_api_context(self):
        url = (
            "https://www.federalregister.gov/documents/2024/05/13/"
            "2024-10533/missing-or-murdered-indigenous-persons-awareness-day-2024"
        )
        title = "Missing or Murdered Indigenous Persons Awareness Day, 2024"
        context = (
            "A Proclamation. For decades, Native communities across this continent have "
            "been devastated by an epidemic of disappearances and killings involving "
            "missing and murdered indigenous persons."
        )
        thin_body = "By the President of the United States of America. A Proclamation."
        verdict = check_document_text(thin_body, url, title=title, context=context)
        assert verdict

    def test_still_rejects_short_federal_register_without_mmip_context(self):
        url = (
            "https://www.federalregister.gov/documents/2024/05/13/"
            "2024-10533/missing-or-murdered-indigenous-persons-awareness-day-2024"
        )
        verdict = check_document_text(
            "Annual budget report for federal agencies.",
            url,
            title="Annual Budget Report",
            context="Fiscal year appropriations summary.",
        )
        assert verdict.code == "doc_too_short"


class TestScreenCandidateDocument:
    def test_url_shape_runs_before_text_check(self):
        verdict = screen_candidate_document(
            "https://www.iowa.gov/search?q=tribal%20missing%20persons", MMIP_DOC
        )
        assert verdict.code == "url_search_page"

    def test_good_candidate_passes(self):
        assert screen_candidate_document("https://dojmt.gov/mmip-home/", MMIP_DOC)


class TestRecordConsistency:
    def _record(self, **overrides):
        record = {
            "Name": "Day of Awareness for Missing and Murdered Indigenous Women",
            "Bill Number": "",
            "Last Update": "2026-05-05",
            "Bill Text": "https://www.doa.nc.gov/news/press-releases/x",
        }
        record.update(overrides)
        return record

    def test_accepts_grounded_record(self):
        record = self._record()
        result = check_record_consistency(record, MMIP_DOC + " Issued 2026-05-05.")
        assert result
        assert result.warnings == []

    def test_blocks_when_document_has_no_mmip_evidence(self):
        result = check_record_consistency(self._record(), "Chapter 181 rule report. " * 40)
        assert not result
        assert result.blocking_code == "doc_no_mmip_evidence"

    def test_blocks_title_that_is_absent_from_the_document(self):
        record = self._record(Name="Tribal Public Safety Funding Reauthorization Statute")
        result = check_record_consistency(record, MMIP_DOC)
        assert not result
        assert result.blocking_code == "title_not_in_document"

    def test_clears_hallucinated_bill_number(self):
        record = self._record(**{"Bill Number": "EO14053"})
        result = check_record_consistency(record, MMIP_DOC + " Issued 2026-05-05.")
        assert result
        assert record["Bill Number"] == ""
        assert any("EO14053" in warning for warning in result.warnings)

    def test_keeps_bill_number_present_in_the_document(self):
        record = self._record(**{"Bill Number": "HB 1234"})
        result = check_record_consistency(
            record, MMIP_DOC + " House Bill HB1234 was enacted on 2026-05-05."
        )
        assert result
        assert record["Bill Number"] == "HB 1234"

    def test_warns_on_ungrounded_january_first_date(self):
        record = self._record(**{"Last Update": "2026-01-01"})
        result = check_record_consistency(record, MMIP_DOC + " Published in 2026.")
        assert result
        assert any("Last Update" in warning for warning in result.warnings)
        assert record["Last Update"] == ""

    def test_accepts_january_first_when_the_document_says_so(self):
        record = self._record(**{"Last Update": "2026-01-01"})
        result = check_record_consistency(record, MMIP_DOC + " Effective January 1, 2026.")
        assert result.warnings == []

    def test_warns_when_year_is_absent_from_the_document(self):
        record = self._record(**{"Last Update": "2019-07-04"})
        result = check_record_consistency(record, MMIP_DOC)
        assert any("Last Update" in warning for warning in result.warnings)
        assert record["Last Update"] == ""

    def test_rejects_year_present_without_matching_calendar_day(self):
        record = self._record(**{"Last Update": "2024-05-05"})
        doc = MMIP_DOC + " Published in 2024."
        result = check_record_consistency(record, doc)
        assert any("Last Update" in warning for warning in result.warnings)
        assert record["Last Update"] == ""

    def test_accepts_month_day_year_phrasing(self):
        record = self._record(**{"Last Update": "2026-05-05"})
        result = check_record_consistency(record, MMIP_DOC + " Proclaimed May 5, 2026.")
        assert result.warnings == []

    def test_clears_ungrounded_sponsors_and_chamber_details(self):
        usao_doc = (
            (MMIP_DOC + " ")
            + (
                "For Immediate Release. U.S. Attorney's Office, District of Alaska. "
                "Today the U.S. Attorney's Office joins communities in recognizing "
                "Missing and Murdered Indigenous Persons Awareness Day. "
                "Thursday, May 5, 2022."
            )
        )
        record = self._record(
            **{
                "Last Update": "2024-05-05",
                "Sponsors of the Legislation": "Governor Mike Dunleavy",
                "Chamber Details": "May 5, 2024: Proclamation issued by Governor Mike Dunleavy",
                "Session": "Dunleavy Administration",
            }
        )
        result = check_record_consistency(record, usao_doc)
        assert result
        assert record["Last Update"] == ""
        assert record["Sponsors of the Legislation"] == ""
        assert record["Chamber Details"] == ""
        assert record["Session"] == ""
        assert any("sponsor" in warning for warning in result.warnings)
        assert any("Chamber Details" in warning for warning in result.warnings)
        assert any("Session" in warning for warning in result.warnings)


def test_title_overlap_ignores_stopwords():
    assert title_overlap("The Act of Bill", "totally unrelated content") == 0.0
    assert title_overlap("Missing Indigenous Relatives", "missing indigenous relatives") == 1.0


def test_merge_warnings_appends_without_duplicates():
    assert merge_warnings("first", ["second", "first"]) == "first; second"
    assert merge_warnings("", ["only"]) == "only"


class TestBillNumberInText:
    @pytest.mark.parametrize(
        "bill_number,source_text",
        [
            ("HB0025", "House Bill H.B. 25 relating to missing persons."),
            ("HB958", "The measure H. R. 958 was referred to committee."),
            ("SB4923", "Senate Bill S. 4923 addresses tribal law enforcement."),
            ("A08545", "Assembly Bill 8545 IN ASSEMBLY calendar for 2026."),
        ],
    )
    def test_audit_formatting_cases(self, bill_number, source_text):
        assert bill_number_in_text(bill_number, source_text)

    def test_zero_padding_and_dots(self):
        assert bill_number_in_text("HB0015", "Prefiled as H.B. 15 for the session.")

    def test_federal_chamber_alias_hr_hb(self):
        assert bill_number_in_text("HR958", "House Bill HB958 was introduced.")

    def test_ny_assembly_spaced_form(self):
        assert bill_number_in_text("A8545", "A. 8545 passed the assembly.")

    def test_admin_order_phrasing(self):
        text = "Governor issued Administrative Order No. 329 on tribal coordination."
        assert bill_number_in_text("AO329", text)

    def test_legiscan_url_fallback(self):
        text = "An act relating to missing indigenous persons."
        bill_data = {
            "Bill Text": "https://legiscan.com/MN/bill/HB0025/2025",
        }
        assert bill_number_in_text("HB0025", text, bill_data=bill_data)

    def test_absent_bill_number(self):
        assert not bill_number_in_text("HB9999", "Unrelated policy memo with no bill cite.")


class TestSourceAwareGrounding:
    def test_legiscan_skips_sponsor_session_chamber_grounding(self):
        record = {
            "Name": "Missing Indigenous Persons Task Force",
            "Bill Number": "",
            "Last Update": "2026-05-05",
            "Bill Text": "https://legiscan.com/MN/bill/SF36/2025",
            "Source": "LegiScan",
            "Sponsors of the Legislation": "Senator Example",
            "Chamber Details": "Introduced in Senate",
            "Session": "2025 Regular Session",
        }
        doc = (MMIP_DOC + " Issued 2026-05-05.") * 2
        result = check_record_consistency(record, doc)
        assert result
        assert record["Sponsors of the Legislation"] == "Senator Example"
        assert record["Chamber Details"] == "Introduced in Senate"
        assert record["Session"] == "2025 Regular Session"
        assert not any("sponsor" in w for w in result.warnings)
        assert not any("Chamber Details" in w for w in result.warnings)
        assert not any("Session" in w for w in result.warnings)

    def test_federal_site_skips_session_only(self):
        record = {
            "Name": "Day of Awareness for Missing and Murdered Indigenous Women",
            "Bill Number": "",
            "Last Update": "2026-05-05",
            "Bill Text": "https://www.justice.gov/usao-ak/pr/example",
            "Source": "Federal Site",
            "Sponsors of the Legislation": "Attorney General",
            "Chamber Details": "Press release issued May 5, 2026",
            "Session": "Biden Administration",
        }
        doc = MMIP_DOC + " Issued 2026-05-05."
        result = check_record_consistency(record, doc)
        assert result
        assert record["Session"] == "Biden Administration"
        assert not any("Session" in w for w in result.warnings)
        assert record["Sponsors of the Legislation"] == ""
        assert any("sponsor" in w for w in result.warnings)
