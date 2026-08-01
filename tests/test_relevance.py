import pytest

from analysis_schema import MMIPRelevanceResult
from analysis_validator import validate_mmip_relevance
from discovery.models import Candidate
from discovery.queries import keyword_prescreen
from discovery.relevance import MMIPRelevanceGate


MMIP_BILL_EXCERPT = """
AN ACT establishing a Missing and Murdered Indigenous Persons task force.
The task force shall study cases of missing and murdered Native American
and Alaska Native people in this state and recommend data collection protocols.
"""

GENERIC_MISSING_EXCERPT = """
AN ACT to establish an AMBER Alert system for missing children and adults.
The clearinghouse shall track all missing persons reports statewide.
"""

TRIBAL_GAMING_EXCERPT = """
AN ACT to authorize tribal gaming compacts and revenue sharing agreements
between the state and federally recognized tribes.
"""


def test_keyword_prescreen_mmip_acronym():
    assert keyword_prescreen("SB 123 MMIP Task Force Act")


def test_keyword_prescreen_indigenous_and_harm():
    assert keyword_prescreen("Missing Indigenous women task force")


def test_keyword_prescreen_generic_missing_fails():
    assert not keyword_prescreen("AMBER Alert for missing children statewide")


def test_keyword_prescreen_tribal_gaming_fails():
    assert not keyword_prescreen("Tribal gaming compact authorization")


def test_validate_mmip_relevance_schema():
    data = {
        "is_mmip": True,
        "confidence": 0.92,
        "rationale": "Establishes MMIP task force for Native American communities.",
        "primary_subject": "MMIP task force",
    }
    result, warnings = validate_mmip_relevance(data)
    assert result is not None
    assert result.is_mmip is True
    assert result.confidence == 0.92
    assert warnings == []


class MockLLMProvider:
    model = "mock-model"

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete_json(self, system, user, schema=None):
        self.calls += 1
        return self.response


def test_relevance_gate_prescreen_fail():
    gate = MMIPRelevanceGate(MockLLMProvider({}), min_confidence=0.6)
    candidate = Candidate(
        source="legiscan",
        state="IA",
        url="https://example.com/bill/1",
        title="AMBER Alert Expansion",
        snippet=GENERIC_MISSING_EXCERPT,
    )
    is_relevant, result, stage = gate.evaluate(candidate, GENERIC_MISSING_EXCERPT)
    assert not is_relevant
    assert stage == "prescreen_fail"
    assert result is None


def test_relevance_gate_llm_relevant():
    gate = MMIPRelevanceGate(
        MockLLMProvider(
            {
                "is_mmip": True,
                "confidence": 0.95,
                "rationale": "MMIP task force for Indigenous communities.",
                "primary_subject": "MMIP task force",
            }
        ),
        min_confidence=0.6,
    )
    candidate = Candidate(
        source="legiscan",
        state="NM",
        url="https://example.com/bill/2",
        title="Missing and Murdered Indigenous Persons Task Force",
        snippet=MMIP_BILL_EXCERPT,
    )
    is_relevant, result, stage = gate.evaluate(candidate, MMIP_BILL_EXCERPT)
    assert is_relevant
    assert stage == "llm"
    assert result.confidence >= 0.6


def test_relevance_gate_llm_not_relevant():
    gate = MMIPRelevanceGate(
        MockLLMProvider(
            {
                "is_mmip": False,
                "confidence": 0.88,
                "rationale": "General missing persons legislation without Indigenous nexus.",
                "primary_subject": "AMBER Alert",
            }
        ),
        min_confidence=0.6,
    )
    candidate = Candidate(
        source="legiscan",
        state="IA",
        url="https://example.com/bill/3",
        title="AMBER Alert Expansion Act",
        snippet=GENERIC_MISSING_EXCERPT,
    )
    # Force past prescreen by using MMIP in title for prescreen but generic excerpt for LLM
    candidate.title = "MMIP AMBER Alert Expansion Act"
    is_relevant, result, stage = gate.evaluate(candidate, GENERIC_MISSING_EXCERPT)
    assert not is_relevant
    assert stage == "llm"
    assert result.is_mmip is False


def test_relevance_gate_confidence_fail():
    gate = MMIPRelevanceGate(
        MockLLMProvider(
            {
                "is_mmip": True,
                "confidence": 0.4,
                "rationale": "Weak Indigenous connection.",
                "primary_subject": "Missing persons",
            }
        ),
        min_confidence=0.6,
    )
    candidate = Candidate(
        source="legiscan",
        state="NY",
        url="https://example.com/bill/4",
        title="MMIP study commission",
        snippet=MMIP_BILL_EXCERPT,
    )
    is_relevant, result, stage = gate.evaluate(candidate, MMIP_BILL_EXCERPT)
    assert not is_relevant
    assert stage == "confidence_fail"
