"""Tests for DOJ / USAO federal jurisdiction inference."""

from discovery.federal_jurisdiction import (
    extract_usao_slug,
    infer_federal_jurisdiction,
    is_national_federal_document,
    resolve_federal_pending_state,
)

AK_MMIP_HUB = "https://www.justice.gov/usao-ak/missing-or-murdered-indigenous-persons"
AK_PR = (
    "https://www.justice.gov/usao-ak/pr/"
    "recognizing-missing-and-murdered-indigenous-persons-awareness-day-alaska"
)
WDMI_PR = "https://www.justice.gov/usao-wdmi/pr/2024_0506_MMIP_March"
SD_PR = (
    "https://www.justice.gov/usao-sd/pr/"
    "justice-department-strengthens-efforts-builds-partnerships-address-crisis-missing-or"
)
DOJ_HQ_OPA = (
    "https://www.justice.gov/archives/opa/pr/"
    "readout-departments-justice-and-interior-roundtable-media-coverage-missing-or-murdered"
)
FR_EO = "https://www.federalregister.gov/documents/2021/11/15/2021-24706/missing-and-murdered-indigenous-persons"


def test_extract_usao_slug_from_url():
    assert extract_usao_slug(AK_PR) == "usao-ak"
    assert extract_usao_slug(WDMI_PR) == "usao-wdmi"


def test_extract_usao_slug_from_source_id():
    assert extract_usao_slug("https://example.com/foo", source_id="usao-ak") == "usao-ak"


def test_alaska_usao_press_release_infers_ak():
    assert infer_federal_jurisdiction(AK_PR, source_id="usao-ak") == "AK"
    assert infer_federal_jurisdiction(AK_MMIP_HUB, source_id="usao-ak") == "AK"


def test_alaska_usao_from_title_fallback_without_usao_path():
    title = "U.S. Attorney's Office, District of Alaska Recognizes MMIP Awareness Day"
    assert infer_federal_jurisdiction("https://www.justice.gov/news/example", title=title) == "AK"


def test_midwestern_usao_wdmi_infers_mi():
    assert infer_federal_jurisdiction(WDMI_PR) == "MI"
    title = "U.S. Attorney's Office for the Western District of Michigan"
    assert infer_federal_jurisdiction(WDMI_PR, title=title) == "MI"


def test_usao_sd_infers_sd_not_national():
    assert infer_federal_jurisdiction(SD_PR) == "SD"


def test_doj_hq_opa_stays_national():
    assert is_national_federal_document(DOJ_HQ_OPA) is True
    assert infer_federal_jurisdiction(DOJ_HQ_OPA) == "National"
    title = "Attorney General Garland Visits New Mexico"
    assert infer_federal_jurisdiction(DOJ_HQ_OPA, title=title) == "National"


def test_federal_register_executive_order_stays_national():
    assert is_national_federal_document(FR_EO, content_type="executive_order") is True
    assert infer_federal_jurisdiction(FR_EO, content_type="executive_order") == "National"


def test_resolve_pending_prefers_url_over_llm_national():
    resolved = resolve_federal_pending_state(
        url=SD_PR,
        candidate_state="SD",
        llm_state="National",
        title="Justice Department Strengthens Efforts in South Dakota",
    )
    assert resolved == "SD"


def test_resolve_pending_keeps_national_for_hq_when_llm_also_national():
    resolved = resolve_federal_pending_state(
        url=DOJ_HQ_OPA,
        candidate_state="National",
        llm_state="National",
        title="Readout: Departments of Justice and Interior Roundtable",
    )
    assert resolved == "National"


def test_resolve_pending_uses_llm_when_url_unambiguous_and_inferred_national():
    resolved = resolve_federal_pending_state(
        url="https://www.justice.gov/opa/pr/state-specific-body-copy-only",
        candidate_state="National",
        llm_state="NC",
        title="Eastern District of North Carolina MMIP event",
        body="The U.S. Attorney's Office for the Eastern District of North Carolina ...",
    )
    assert resolved == "NC"
