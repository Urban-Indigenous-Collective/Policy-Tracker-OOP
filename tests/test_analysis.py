import pytest

from analysis_schema import BillAnalysis, EvalAnswer
from analysis_validator import (
    quote_in_source,
    strip_preamble,
    validate_bill_analysis,
    validate_categories,
    normalize_expl_for_eval,
)
from constants import ALLOWED_CATEGORIES


SAMPLE_BILL = """
Section 1. Establishes a missing persons unit within the division of state police.
The unit shall submit an annual report to the governor and legislature regarding
the activities of the clearinghouse including statistical information involving
reported cases of missing persons.
Section 2. Adds women to the responsibility of the missing persons clearinghouse.
"""


def test_strip_preamble():
    assert strip_preamble("Here is a summary of the bill.") == "summary of the bill."


def test_normalize_expl_for_no_eval():
    assert normalize_expl_for_eval(EvalAnswer.NO, "Some long explanation") == "No"


def test_quote_in_source_found():
    quote = "submit an annual report to the governor and legislature"
    assert quote_in_source(quote, SAMPLE_BILL)


def test_quote_in_source_missing():
    assert not quote_in_source("this text does not exist in the bill", SAMPLE_BILL)


def test_validate_categories_valid():
    assert validate_categories(["Data Collection", "Taskforce"]) == []


def test_validate_categories_invalid():
    errors = validate_categories(["Not A Real Category"])
    assert len(errors) == 1


def test_bill_analysis_schema_enums():
    data = {
        "summary": "Short summary.",
        "gender_inclusive_eval": "No",
        "gender_inclusive_expl": "No",
        "mechanisms_eval": "Yes",
        "mechanisms_expl": [
            "submit an annual report to the governor and legislature regarding the activities"
        ],
        "prevention_efforts_eval": "No",
        "prevention_efforts_expl": [],
        "centering_indigenous_voices_eval": "No",
        "centering_indigenous_voices_expl": "No",
        "survivor_relative_input_eval": "No",
        "survivor_relative_input_expl": "No",
        "categories": ["Data Collection"],
    }
    analysis, warnings = validate_bill_analysis(data, SAMPLE_BILL)
    assert analysis is not None
    assert analysis.mechanisms_eval == EvalAnswer.YES
    assert analysis.gender_inclusive_eval == EvalAnswer.NO
    assert analysis.gender_inclusive_expl == "No"


def test_bill_analysis_consistency_golden():
    data = {
        "summary": "Establishes a missing persons unit.",
        "gender_inclusive_eval": "No.",
        "gender_inclusive_expl": "Focused on women and children.",
        "mechanisms_eval": "yes",
        "mechanisms_expl": ["submit an annual report to the governor and legislature"],
        "prevention_efforts_eval": "No",
        "prevention_efforts_expl": "No",
        "centering_indigenous_voices_eval": "Somewhat",
        "centering_indigenous_voices_expl": "Limited mention.",
        "survivor_relative_input_eval": "No",
        "survivor_relative_input_expl": "No.",
        "categories": "Data Collection",
    }
    first, _ = validate_bill_analysis(data, SAMPLE_BILL)
    second, _ = validate_bill_analysis(data, SAMPLE_BILL)
    assert first.model_dump() == second.model_dump()


class MockLLMProvider:
    model = "mock-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete_json(self, system, user, schema=None):
        result = self.responses[self.calls]
        self.calls += 1
        return result

    def complete_text(self, system, user):
        return "text"

    def complete_vision(self, prompt, image_b64):
        return "ocr text"


def test_bill_analyzer_integration_smoke():
    from bill_analyzer import BillAnalyzer

    analysis_payload = {
        "summary": "Test summary.",
        "gender_inclusive_eval": "No",
        "gender_inclusive_expl": "No",
        "mechanisms_eval": "Yes",
        "mechanisms_expl": ["submit an annual report to the governor and legislature"],
        "prevention_efforts_eval": "No",
        "prevention_efforts_expl": [],
        "centering_indigenous_voices_eval": "No",
        "centering_indigenous_voices_expl": "No",
        "survivor_relative_input_eval": "No",
        "survivor_relative_input_expl": "No",
        "categories": ["Data Collection"],
    }
    pros_cons_payload = {
        "uic_pros": ["Establishes specialized unit."],
        "uic_cons": ["Limited gender inclusivity."],
    }
    provider = MockLLMProvider([analysis_payload, pros_cons_payload])
    analyzer = BillAnalyzer(provider, cache_dir="/tmp/policy-tracker-test-cache")
    analyzer.cache_enabled = False
    result = analyzer.run_full_analysis(SAMPLE_BILL, "")
    assert result["gender_inclusive_eval"] == "No"
    assert result["mechanisms_eval"] == "Yes"
    assert "1." in result["uic_pros"]
    assert provider.calls == 2
