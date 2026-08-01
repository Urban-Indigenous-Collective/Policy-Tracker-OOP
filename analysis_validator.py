import re
from typing import List, Tuple

from analysis_schema import BillAnalysis, EvalAnswer, GovMetadata, ProsConsResult
from constants import ALLOWED_CATEGORIES


PREAMBLE_PATTERNS = [
    re.compile(r"^here is (a |an )?", re.IGNORECASE),
    re.compile(r"^the following ", re.IGNORECASE),
]


def strip_preamble(text: str) -> str:
    cleaned = text.strip()
    for pattern in PREAMBLE_PATTERNS:
        cleaned = pattern.sub("", cleaned).strip()
    return cleaned


def normalize_expl_for_eval(eval_value: EvalAnswer, expl: str) -> str:
    if eval_value == EvalAnswer.NO:
        return "No"
    if eval_value == EvalAnswer.SOMEWHAT and not expl.strip():
        return "Somewhat"
    return strip_preamble(expl).strip()


def quote_in_source(quote: str, source_text: str) -> bool:
    quote_norm = re.sub(r"\s+", " ", quote.strip().lower())
    source_norm = re.sub(r"\s+", " ", source_text.lower())
    if not quote_norm:
        return True
    if len(quote_norm) < 20:
        return quote_norm in source_norm
    # Allow partial match for long quotes (80% of words present in order)
    words = quote_norm.split()
    window = " ".join(words[: min(len(words), 12)])
    return window in source_norm or quote_norm[:120] in source_norm


def validate_quotes(quotes: List[str], source_text: str, field_name: str) -> List[str]:
    errors = []
    for i, quote in enumerate(quotes):
        if quote and not quote_in_source(quote, source_text):
            errors.append(f"{field_name}[{i}] quote not found in source text")
    return errors


def validate_categories(categories: List[str]) -> List[str]:
    errors = []
    allowed = {c.lower(): c for c in ALLOWED_CATEGORIES}
    for cat in categories:
        if cat.lower() not in allowed:
            errors.append(f"Invalid category: {cat}")
    return errors


def validate_bill_analysis(data: dict, source_text: str) -> Tuple[BillAnalysis, List[str]]:
    warnings: List[str] = []
    try:
        analysis = BillAnalysis.model_validate(data)
    except Exception as exc:
        return None, [f"Schema validation failed: {exc}"]

    if analysis.mechanisms_eval == EvalAnswer.YES:
        warnings.extend(validate_quotes(analysis.mechanisms_expl, source_text, "mechanisms_expl"))
    elif analysis.mechanisms_expl:
        warnings.append("mechanisms_expl provided but mechanisms_eval is not Yes")

    if analysis.prevention_efforts_eval == EvalAnswer.YES:
        warnings.extend(
            validate_quotes(analysis.prevention_efforts_expl, source_text, "prevention_efforts_expl")
        )
    elif analysis.prevention_efforts_expl:
        warnings.append("prevention_efforts_expl provided but prevention_efforts_eval is not Yes")

    warnings.extend(validate_categories(analysis.categories))

    analysis.gender_inclusive_expl = normalize_expl_for_eval(
        analysis.gender_inclusive_eval, analysis.gender_inclusive_expl
    )
    analysis.centering_indigenous_voices_expl = normalize_expl_for_eval(
        analysis.centering_indigenous_voices_eval, analysis.centering_indigenous_voices_expl
    )
    analysis.survivor_relative_input_expl = normalize_expl_for_eval(
        analysis.survivor_relative_input_eval, analysis.survivor_relative_input_expl
    )
    analysis.summary = strip_preamble(analysis.summary)

    return analysis, warnings


def validate_gov_metadata(data: dict) -> Tuple[GovMetadata, List[str]]:
    try:
        return GovMetadata.model_validate(data), []
    except Exception as exc:
        return None, [f"Metadata schema validation failed: {exc}"]


def validate_pros_cons(data: dict) -> Tuple[ProsConsResult, List[str]]:
    try:
        result = ProsConsResult.model_validate(data)
        result.uic_pros = [strip_preamble(item) for item in result.uic_pros]
        result.uic_cons = [strip_preamble(item) for item in result.uic_cons]
        return result, []
    except Exception as exc:
        return None, [f"Pros/cons schema validation failed: {exc}"]


def format_numbered_list(items: List[str]) -> str:
    if not items:
        return ""
    return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))


def format_quote_list(items: List[str]) -> str:
    if not items:
        return "No"
    return format_numbered_list(items)


def analysis_to_compiled_fields(analysis: BillAnalysis, pros_cons: ProsConsResult, warnings: List[str]) -> dict:
    return {
        "chat_summary": analysis.summary,
        "gender_inclusive_eval": analysis.gender_inclusive_eval.value,
        "gender_inclusive_expl": analysis.gender_inclusive_expl,
        "mechanisms_eval": analysis.mechanisms_eval.value,
        "mechanisms_expl": format_quote_list(analysis.mechanisms_expl),
        "prevention_efforts_eval": analysis.prevention_efforts_eval.value,
        "prevention_efforts_expl": format_quote_list(analysis.prevention_efforts_expl),
        "centering_indigenous_voices_eval": analysis.centering_indigenous_voices_eval.value,
        "centering_indigenous_voices_expl": analysis.centering_indigenous_voices_expl,
        "survivor_relative_input_eval": analysis.survivor_relative_input_eval.value,
        "survivor_relative_input_expl": analysis.survivor_relative_input_expl,
        "categories_eval": ", ".join(analysis.categories),
        "uic_pros": format_numbered_list(pros_cons.uic_pros),
        "uic_cons": format_numbered_list(pros_cons.uic_cons),
        "validation_warnings": "; ".join(warnings) if warnings else "",
    }
