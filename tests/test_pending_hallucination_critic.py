"""Tests for pending_hallucination_critic."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pending_hallucination_critic import (
    CriticSeverity,
    FieldVerdict,
    HallucinationCriticResult,
    build_analysis_block,
    build_critic_user_prompt,
    run_critic,
    validate_critic_result,
)


def test_validate_critic_result_parses_issues():
    raw = {
        "is_grounded": False,
        "confidence": 0.85,
        "overall_rationale": "Summary overclaims scope.",
        "issues": [
            {
                "field": "Summary",
                "severity": "overstated",
                "claim": "Creates a statewide task force",
                "rationale": "Document only studies the issue",
                "suggested_action": "flag",
            }
        ],
        "field_verdicts": {"Summary": "suspect", "UIC Pros": "ok"},
    }
    result, warnings = validate_critic_result(raw)
    assert warnings == []
    assert result is not None
    assert result.is_grounded is False
    assert result.issues[0].severity == CriticSeverity.OVERSTATED
    assert result.field_verdicts["Summary"] == FieldVerdict.SUSPECT


def test_validate_critic_result_rejects_bad_payload():
    result, warnings = validate_critic_result({"confidence": "not-a-float"})
    assert result is None
    assert warnings


def test_build_analysis_block_includes_summary_and_excerpt():
    fields = {
        "Name": "MMIP Task Force Bill",
        "State": "UT",
        "Source": "LegiScan",
        "Summary": "Establishes a task force on MMIP.",
        "Gender Inclusive Language?": "Yes",
        "Gender Inclusive Language": "Uses women and girls.",
        "Categories": ["Taskforce"],
        "UIC Pros": "1. Strengthens coordination",
    }
    block = build_analysis_block(fields)
    assert "Summary: Establishes a task force on MMIP." in block
    assert "Gender Inclusive Language?: Yes" in block
    assert "Categories: Taskforce" in block

    prompt = build_critic_user_prompt(fields, "SECTION 1. Task force established.", excerpt_chars=100)
    assert "MMIP Task Force Bill" in prompt
    assert "SECTION 1. Task force established." in prompt
    assert "Establishes a task force on MMIP." in prompt


def test_run_critic_uses_llm_complete_json():
    llm = MagicMock()
    llm.complete_json.return_value = {
        "is_grounded": True,
        "confidence": 0.9,
        "overall_rationale": "All fields supported.",
        "issues": [],
        "field_verdicts": {"Summary": "ok"},
    }
    fields = {"Name": "Test", "Summary": "Supported summary."}
    result, warnings = run_critic(llm, fields, "Supported summary in source.")
    assert warnings == []
    assert result is not None
    assert result.is_grounded is True
    llm.complete_json.assert_called_once()
    _system, user = llm.complete_json.call_args[0][:2]
    assert "Supported summary." in user


def test_has_issues_property():
    result = HallucinationCriticResult(
        is_grounded=False,
        issues=[],
        field_verdicts={"Summary": FieldVerdict.BAD},
    )
    assert result.has_issues is True
    assert result.suspect_or_bad_fields == ["Summary"]
