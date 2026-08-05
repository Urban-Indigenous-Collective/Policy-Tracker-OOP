import pytest

from analysis_schema import BillAnalysis, EvalAnswer
from analysis_validator import validate_bill_analysis
from eval_expl_adjudication import (
    AdjudicationAction,
    adjudicate_eval_expl,
    apply_safe_fixes,
    classify_doc_type,
    quote_establishes,
)

BILL_TEXT = """
AN ACT relating to missing persons.
Be it enacted by the legislature:
Section 1. The division shall establish a missing persons unit.
The unit shall submit an annual report to the governor.
Section 2. Officers shall complete a minimum of 8 hours of training.
"""

PROCLAMATION_TEXT = """
BY THE PRESIDENT OF THE UNITED STATES OF AMERICA
A PROCLAMATION
Whereas we honor the lives of missing and murdered Indigenous women;
Whereas the Department of Justice has developed a new unit and launched
outreach programs; Now, therefore, I proclaim May 5 as a day of awareness.
"""

PDF_JUNK_QUOTE = "E:\\BILLS\\119\\H\\H3198\\IH\\H3198.IH.xml"


def _analysis(**overrides) -> BillAnalysis:
    data = {
        "summary": "Test.",
        "gender_inclusive_eval": "No",
        "gender_inclusive_expl": "No",
        "mechanisms_eval": "No",
        "mechanisms_expl": [],
        "prevention_efforts_eval": "No",
        "prevention_efforts_expl": [],
        "centering_indigenous_voices_eval": "No",
        "centering_indigenous_voices_expl": "No",
        "survivor_relative_input_eval": "No",
        "survivor_relative_input_expl": "No",
        "categories": ["Data Collection"],
    }
    data.update(overrides)
    return BillAnalysis.model_validate(data)


def test_classify_doc_type_bill():
    assert classify_doc_type("HB 123", BILL_TEXT, "") == "bill"


def test_classify_doc_type_proclamation():
    assert classify_doc_type("Awareness Day", PROCLAMATION_TEXT, "") == "proclamation"


def test_quote_establishes_obligation():
    est, ment = quote_establishes("The unit shall submit an annual report", "bill")
    assert est is True
    assert ment is False


def test_quote_establishes_mentions_only_in_proclamation():
    est, ment = quote_establishes(
        "the Department of Justice has developed a new unit", "proclamation"
    )
    assert est is False
    assert ment is True


def test_adjudicate_pdf_junk_clears_expl():
    analysis = _analysis(
        mechanisms_eval="No",
        mechanisms_expl=[PDF_JUNK_QUOTE],
    )
    adj = adjudicate_eval_expl(analysis, BILL_TEXT)
    assert adj.mech.action == AdjudicationAction.CLEAR_EXPL
    fixes = apply_safe_fixes(analysis, adj)
    assert analysis.mechanisms_expl == []
    assert fixes


def test_adjudicate_proclamation_clears_expl():
    analysis = _analysis(
        mechanisms_eval="No",
        mechanisms_expl=["the Department of Justice has developed a new unit"],
    )
    adj = adjudicate_eval_expl(
        analysis,
        PROCLAMATION_TEXT,
        name="Awareness Day Proclamation",
    )
    assert adj.mech.action == AdjudicationAction.CLEAR_EXPL
    apply_safe_fixes(analysis, adj)
    assert analysis.mechanisms_expl == []


def test_adjudicate_bill_flips_eval():
    analysis = _analysis(
        mechanisms_eval="No",
        mechanisms_expl=["The unit shall submit an annual report to the governor"],
    )
    adj = adjudicate_eval_expl(analysis, BILL_TEXT, name="HB 100")
    assert adj.mech.action == AdjudicationAction.FLIP_EVAL_YES
    apply_safe_fixes(analysis, adj)
    assert analysis.mechanisms_eval == EvalAnswer.YES


def test_adjudicate_training_flips_prevention_eval():
    analysis = _analysis(
        prevention_efforts_eval="No",
        prevention_efforts_expl=["Officers shall complete a minimum of 8 hours of training"],
    )
    adj = adjudicate_eval_expl(analysis, BILL_TEXT, name="HB 100")
    assert adj.prev.action == AdjudicationAction.FLIP_EVAL_YES


def test_validate_bill_analysis_applies_fixes():
    data = {
        "summary": "Test.",
        "gender_inclusive_eval": "No",
        "gender_inclusive_expl": "No",
        "mechanisms_eval": "No",
        "mechanisms_expl": [PDF_JUNK_QUOTE],
        "prevention_efforts_eval": "No",
        "prevention_efforts_expl": [],
        "centering_indigenous_voices_eval": "No",
        "centering_indigenous_voices_expl": "No",
        "survivor_relative_input_eval": "No",
        "survivor_relative_input_expl": "No",
        "categories": ["Data Collection"],
    }
    analysis, warnings = validate_bill_analysis(
        data,
        BILL_TEXT,
        apply_eval_expl_fixes=True,
    )
    assert analysis.mechanisms_expl == []
    assert not any("mechanisms_expl provided" in w for w in warnings)
    assert any(w.startswith("eval_expl_fix:") for w in warnings)


def test_validate_bill_analysis_suppresses_none_adjudication_mismatch():
    """eval≠Yes with expl quotes is not warned when adjudication action is NONE."""
    data = {
        "summary": "Test.",
        "gender_inclusive_eval": "No",
        "gender_inclusive_expl": "No",
        "mechanisms_eval": "No",
        "mechanisms_expl": [],
        "prevention_efforts_eval": "No",
        "prevention_efforts_expl": [
            "engaging men in preventing violence",
            "expand programs focused on increasing legal assistance",
        ],
        "centering_indigenous_voices_eval": "No",
        "centering_indigenous_voices_expl": "No",
        "survivor_relative_input_eval": "No",
        "survivor_relative_input_expl": "No",
        "categories": ["Data Collection"],
    }
    resolution_text = """
    A CONCURRENT RESOLUTION urging Congress to reauthorize the Violence Against Women Act.
    Resolved, that Congress should reauthorize programs engaging men in preventing violence
    and expand programs focused on increasing legal assistance for survivors.
    """
    analysis, warnings = validate_bill_analysis(
        data,
        resolution_text,
        record_name="ACR111 Violence Against Women Act",
        record_url="https://legiscan.com/NJ/bill/ACR111/2024",
    )
    assert analysis is not None
    assert not any("prevention_efforts_expl provided" in w for w in warnings)
    assert not any("mechanisms_expl provided" in w for w in warnings)


def test_validate_bill_analysis_keeps_mismatch_when_adjudication_requires_action():
    data = {
        "summary": "Test.",
        "gender_inclusive_eval": "No",
        "gender_inclusive_expl": "No",
        "mechanisms_eval": "No",
        "mechanisms_expl": ["The unit shall submit an annual report to the governor"],
        "prevention_efforts_eval": "No",
        "prevention_efforts_expl": [],
        "centering_indigenous_voices_eval": "No",
        "centering_indigenous_voices_expl": "No",
        "survivor_relative_input_eval": "No",
        "survivor_relative_input_expl": "No",
        "categories": ["Data Collection"],
    }
    _, warnings = validate_bill_analysis(data, BILL_TEXT, record_name="HB 100")
    assert any("mechanisms_expl provided" in w for w in warnings)
