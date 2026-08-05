import pytest

from quote_repair import find_best_source_span, normalize_for_match, repair_quote_list

SAMPLE_BILL = """
Section 1. Establishes a missing persons unit within the division of state police.
The unit shall submit an annual report to the governor and legislature regarding
the activities of the clearinghouse including statistical information involving
reported cases of missing persons.
Section 2. Adds women to the responsibility of the missing persons clearinghouse.
"""


def test_normalize_for_match_smart_quotes():
    curly = "\u201cthe report\u201d"
    straight = '"the report"'
    assert normalize_for_match(curly) == normalize_for_match(straight)


def test_find_best_source_span_exact():
    quote = "submit an annual report to the governor and legislature"
    span = find_best_source_span(quote, SAMPLE_BILL)
    assert span is not None
    assert span in SAMPLE_BILL


def test_find_best_source_span_paraphrase():
    paraphrase = (
        "The unit will submit an annual report to the governor and legislature regarding "
        "clearinghouse activities"
    )
    span = find_best_source_span(paraphrase, SAMPLE_BILL, min_ratio=0.55)
    assert span is not None
    assert "annual report" in span.lower()


def test_repair_quote_list_replaces_with_verbatim():
    paraphrased = [
        "submit an annual report to the governor and legislature regarding the activities"
    ]
    repaired, warnings = repair_quote_list(paraphrased, SAMPLE_BILL)
    assert not warnings
    assert repaired[0] in SAMPLE_BILL


def test_repair_quote_list_unanchored():
    repaired, warnings = repair_quote_list(
        ["this language does not exist anywhere in the document at all"],
        SAMPLE_BILL,
    )
    assert not repaired
    assert warnings
