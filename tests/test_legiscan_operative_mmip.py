"""LegiScan gate: operative MMIP vs findings-only false positives."""

import pytest

from content_guard import check_legiscan_document_text, check_legiscan_operative_mmip


def _pad(text: str, repeats: int = 4) -> str:
    filler = "Additional implementing language for fiscal and administrative compliance. " * 20
    return (text.strip() + " " + filler) * repeats


SB14_LIKE = _pad(
    """
    SECTION 1. The Legislature finds and declares all of the following:
    (a) Human trafficking is a serious crime affecting many communities.
    (e) Native American women and girls are victims of human trafficking at a much
    higher rate compared to other populations in California.
    SECTION 2. Existing law defines the term serious felony for various purposes.
    SECTION 3. This bill adds human trafficking to the list of serious felonies
    punishable under state law and directs courts to apply enhanced penalties.
    """
)

AB2022_LIKE = _pad(
    """
    SECTION 1. The Legislature finds and declares all of the following:
    (a) Place names using offensive slurs harm racial minorities.
    (c) Offensive names contribute to the current crisis of missing and murdered
    indigenous people across California.
    SECTION 2. The Natural Resources Agency shall review geographic feature names
    and recommend replacements that honor tribes and indigenous languages in each
    region without reference to law enforcement data systems or case review programs.
    """
)

SB823_LIKE = _pad(
    """
    SECTION 1. This act shall be known as the Public Health Omnibus Act of 2021.
    SECTION 2. The Department of Public Health shall administer grants for rural
    clinic staffing, vaccine distribution, maternal health outreach, and tribal
    health clinic infrastructure improvements in underserved counties statewide.
    SECTION 3. Appropriations from the General Fund shall cover implementation costs
    for county public health departments through the fiscal year ending June 30.
    """
)

AB44_LIKE = _pad(
    """
    SECTION 1. The Legislature finds and declares all of the following:
    (b) California has the fifth largest caseload of missing and murdered Indigenous
    women and people, and Indigenous women go missing at rates higher than any other
    ethnic group in the United States.
    SECTION 2. The California Law Enforcement Telecommunications System (CLETS) shall
    grant access to qualified tribal police departments for criminal justice data
    exchange, including missing persons records and wanted-person inquiries.
    """
)

AB134_LIKE = _pad(
    """
    SECTION 1. The Legislature finds public safety collaboration is essential.
    SECTION 2. The Department of Justice shall establish a Tribal Police Pilot
    Program to improve coordination on Missing and Murdered Indigenous Persons cases
    between tribal law enforcement agencies and state investigative units statewide.
    """
)


class TestLegiscanOperativeMmipGate:
    @pytest.mark.parametrize(
        "text,title,code",
        [
            (SB14_LIKE, "Serious felonies: human trafficking.", "legiscan_junk_title"),
            (AB2022_LIKE, "State government.", "legiscan_findings_only_mmip"),
        ],
    )
    def test_rejects_findings_only_or_junk_titles(self, text, title, code):
        verdict = check_legiscan_document_text(text, "https://legiscan.com/CA/bill/X/2023", title=title)
        assert not verdict
        assert verdict.code == code

    def test_rejects_omnibus_without_mmip_signal(self):
        verdict = check_legiscan_document_text(
            SB823_LIKE,
            "https://legiscan.com/CA/bill/SB823/2021",
            title="Public health: omnibus bill.",
        )
        assert not verdict
        assert verdict.code in {"doc_no_mmip_evidence", "legiscan_junk_title"}

    @pytest.mark.parametrize(
        "text,title",
        [
            (AB44_LIKE, "California Law Enforcement Telecommunications System: tribal police."),
            (AB134_LIKE, "Public Safety."),
        ],
    )
    def test_allows_operative_tribal_le_or_mmip(self, text, title):
        assert check_legiscan_document_text(text, "https://legiscan.com/CA/bill/X/2023", title=title)

    def test_explicit_mmip_title_passes_even_with_findings_preamble(self):
        text = _pad(
            """
            SECTION 1. The Legislature finds indigenous communities face violence.
            SECTION 2. The department shall publish an annual report on agency budgets.
            """
        )
        title = "Missing or Murdered Indigenous Women Task Force."
        assert check_legiscan_document_text(text, "https://legiscan.com/CA/bill/X/2019", title=title)

    def test_operative_mmip_without_findings_passes(self):
        text = _pad(
            """
            SECTION 1. This act adds a new program.
            SECTION 2. Counties shall coordinate on missing and murdered indigenous
            persons cold case reviews and share data with tribal partners annually.
            """
        )
        assert check_legiscan_operative_mmip(text, title="County coordination.")


def test_legiscan_relevance_supported_rejects_unrelated_bills():
    from content_guard import legiscan_relevance_supported

    assert not legiscan_relevance_supported(
        "SECTION 2. Medical practices shall publish standard charges.",
        title="Healthcare price transparency",
    )
    assert not legiscan_relevance_supported(
        "SECTION 2. Budget reserve transfer to general fund.",
        title="Budget reserve account transfer; appropriation",
    )


def test_legiscan_relevance_supported_accepts_real_mmip():
    from content_guard import legiscan_relevance_supported

    assert legiscan_relevance_supported(AB44_LIKE, title="MMIP task force extension")
