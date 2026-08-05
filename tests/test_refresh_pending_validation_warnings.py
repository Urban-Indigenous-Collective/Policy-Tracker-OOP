"""Tests for refresh_pending_validation_warnings write-path coercion."""

from analysis_schema import BillAnalysis, EvalAnswer
from analysis_validator import validate_bill_analysis

from scripts.refresh_pending_validation_warnings import (
    _airtable_updates_from_compiled,
    _analysis_from_fields,
    _prepare_updates,
    _strip_eval_expl_fix_warnings,
)


def test_prepare_updates_coerces_comma_string_categories():
    compiled = {"categories_eval": "Taskforce, Data Collection"}
    updates = _airtable_updates_from_compiled(compiled)
    prepared = _prepare_updates(updates, {})
    assert prepared["Categories"] == ["Taskforce", "Data Collection"]


def test_prepare_updates_coerces_python_repr_categories():
    compiled = {"categories_eval": "['Day of Recognition', 'US Law Enforcement']"}
    updates = _airtable_updates_from_compiled(compiled)
    prepared = _prepare_updates(updates, {})
    assert prepared["Categories"] == ["Day of Recognition", "US Law Enforcement"]


def test_prepare_updates_preserves_existing_when_coerce_empty():
    compiled = {"categories_eval": "Totally Invalid Category"}
    updates = _airtable_updates_from_compiled(compiled)
    existing = {"Categories": ["Taskforce"]}
    prepared = _prepare_updates(updates, existing)
    assert prepared["Categories"] == ["Taskforce"]


def test_prepare_updates_omits_categories_when_bad_and_no_existing():
    compiled = {"categories_eval": "Totally Invalid Category"}
    updates = _airtable_updates_from_compiled(compiled)
    prepared = _prepare_updates(updates, {})
    assert "Categories" not in prepared


def test_analysis_from_fields_passes_string_evals_not_enums():
    """EvalAnswer enums must not reach model_validate (str(enum) coerces to No)."""
    fields = {
        "Summary": "Test summary.",
        "Gender Inclusive Language?": "Yes",
        "Gender Inclusive Language": "Uses inclusive terms.",
        "Mechanisms for Evaluation?": "Yes",
        "Mechanisms for Evaluation": "1. Annual report required.",
        "Prevention Efforts?": "Somewhat",
        "Prevention Efforts": "1. Outreach program.",
        "Centering of Indigenous Voices?": "No",
        "Centering of Indigenous Voices": "No",
        "Level of Survivor / Relative Input?": "No",
        "Level of Survivor / Relative Input": "No",
        "Categories": ["Taskforce"],
    }
    data = _analysis_from_fields(fields)
    for key in (
        "gender_inclusive_eval",
        "mechanisms_eval",
        "prevention_efforts_eval",
        "centering_indigenous_voices_eval",
        "survivor_relative_input_eval",
    ):
        assert isinstance(data[key], str), f"{key} should be str, got {type(data[key])}"
        assert not str(data[key]).startswith("EvalAnswer.")

    analysis = BillAnalysis.model_validate(data)
    assert analysis.gender_inclusive_eval == EvalAnswer.YES
    assert analysis.mechanisms_eval == EvalAnswer.YES
    assert analysis.prevention_efforts_eval == EvalAnswer.SOMEWHAT
    assert analysis.centering_indigenous_voices_eval == EvalAnswer.NO


def test_analysis_from_fields_yes_eval_not_coerced_to_no():
    """Regression: enum objects in _analysis_from_fields flipped Yes -> No."""
    fields = {
        "Summary": "Test.",
        "Gender Inclusive Language?": "No",
        "Gender Inclusive Language": "No",
        "Mechanisms for Evaluation?": "Yes",
        "Mechanisms for Evaluation": "1. Requires evaluation metrics.",
        "Prevention Efforts?": "No",
        "Prevention Efforts": "",
        "Centering of Indigenous Voices?": "No",
        "Centering of Indigenous Voices": "No",
        "Level of Survivor / Relative Input?": "No",
        "Level of Survivor / Relative Input": "No",
        "Categories": ["Taskforce"],
    }
    data = _analysis_from_fields(fields)
    analysis, warnings = validate_bill_analysis(data, "Requires evaluation metrics annually.")
    assert analysis is not None
    assert analysis.mechanisms_eval == EvalAnswer.YES
    assert not any("mechanisms_expl provided but mechanisms_eval is not Yes" in w for w in warnings)


def test_strip_eval_expl_fix_warnings():
    raw = (
        "mechanisms_expl[0] quote not found; "
        "eval_expl_fix: mechanisms: cleared expl (pdf junk); "
        "prevention_efforts_expl provided but prevention_efforts_eval is not Yes"
    )
    stripped = _strip_eval_expl_fix_warnings(raw)
    assert "eval_expl_fix:" not in stripped
    assert "mechanisms_expl[0]" in stripped
    assert "prevention_efforts_expl provided" in stripped
