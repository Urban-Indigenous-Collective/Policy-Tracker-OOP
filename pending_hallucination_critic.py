"""Skeptical second-pass auditor for Pending analysis soft fields.

Given source text and existing Pending analysis fields, flags claims that are
not supported by the document excerpt. Report-only — does not rewrite analysis.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

DEFAULT_EXCERPT_CHARS = 12000

CRITIC_SYSTEM = (
    "You are a skeptical auditor for Urban Indigenous Collective's policy tracker. "
    "Review an existing bill analysis against the source document excerpt. "
    "Only flag claims that are NOT supported by the excerpt. "
    "Do not invent new analysis or rewrite fields. "
    "When in doubt, mark a field ok rather than suspect. "
    "Return only valid JSON."
)

CRITIC_SCHEMA = {
    "is_grounded": "boolean — true if all soft analysis fields are adequately supported",
    "confidence": "float 0.0-1.0 — confidence in your audit verdict",
    "overall_rationale": "brief summary of the audit",
    "issues": [
        {
            "field": "Airtable field name (e.g. Summary, UIC Pros)",
            "severity": "ungrounded | overstated | contradicts_eval | fabricated_quote | wrong_category",
            "claim": "the specific unsupported claim",
            "rationale": "why it is unsupported",
            "suggested_action": "flag | clear_field | downgrade_eval | reanalyze",
        }
    ],
    "field_verdicts": {
        "Summary": "ok | suspect | bad",
        "Gender Inclusive Language": "ok | suspect | bad",
        "Centering of Indigenous Voices": "ok | suspect | bad",
        "Level of Survivor / Relative Input": "ok | suspect | bad",
        "UIC Pros": "ok | suspect | bad",
        "UIC Cons": "ok | suspect | bad",
        "Categories": "ok | suspect | bad",
        "Mechanisms for Evaluation": "ok | suspect | bad",
        "Prevention Efforts": "ok | suspect | bad",
    },
}

CRITIC_USER_TEMPLATE = """Record: {name}
State: {state}
Source: {source}
URL: {url}

Existing analysis (soft / judgment fields):
{analysis_block}

Source document excerpt:
{excerpt}

Audit instructions:
1. Check Summary, free-text explanations, UIC Pros/Cons, and Categories against the excerpt.
2. Flag eval↔expl contradictions (e.g. eval=Yes but explanation says No or lacks support).
3. For Mechanisms/Prevention quote lists: only flag if eval=Yes and quoted text clearly does NOT
   establish obligations or prevention programs described in the eval.
4. Do NOT flag minor paraphrasing when the substance is supported.
5. Do NOT flag metadata formatting issues (bill numbers, dates) — those are handled elsewhere.
6. severity=suspect-level issues should use field_verdicts=suspect; reserve bad for clear hallucinations.

Return your audit as JSON."""


class CriticSeverity(str, Enum):
    UNGROUNDED = "ungrounded"
    OVERSTATED = "overstated"
    CONTRADICTS_EVAL = "contradicts_eval"
    FABRICATED_QUOTE = "fabricated_quote"
    WRONG_CATEGORY = "wrong_category"


class FieldVerdict(str, Enum):
    OK = "ok"
    SUSPECT = "suspect"
    BAD = "bad"


class CriticIssue(BaseModel):
    field: str
    severity: CriticSeverity
    claim: str = ""
    rationale: str = ""
    suggested_action: str = "flag"

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: Any) -> CriticSeverity:
        text = str(value or "ungrounded").strip().lower()
        for item in CriticSeverity:
            if item.value == text:
                return item
        return CriticSeverity.UNGROUNDED

    @field_validator("suggested_action", mode="before")
    @classmethod
    def normalize_action(cls, value: Any) -> str:
        text = str(value or "flag").strip().lower()
        allowed = {"flag", "clear_field", "downgrade_eval", "reanalyze"}
        return text if text in allowed else "flag"


class HallucinationCriticResult(BaseModel):
    is_grounded: bool = True
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    overall_rationale: str = ""
    issues: list[CriticIssue] = Field(default_factory=list)
    field_verdicts: dict[str, FieldVerdict] = Field(default_factory=dict)

    @field_validator("field_verdicts", mode="before")
    @classmethod
    def normalize_verdicts(cls, value: Any) -> dict[str, FieldVerdict]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, FieldVerdict] = {}
        for key, raw in value.items():
            if isinstance(raw, FieldVerdict):
                out[str(key)] = raw
                continue
            text = str(raw or "ok").strip().lower()
            try:
                out[str(key)] = FieldVerdict(text)
            except ValueError:
                out[str(key)] = FieldVerdict.OK
        return out

    @property
    def has_issues(self) -> bool:
        return bool(self.issues) or any(v != FieldVerdict.OK for v in self.field_verdicts.values())

    @property
    def suspect_or_bad_fields(self) -> list[str]:
        return [k for k, v in self.field_verdicts.items() if v != FieldVerdict.OK]


SOFT_FIELD_NAMES = (
    "Summary",
    "Gender Inclusive Language?",
    "Gender Inclusive Language",
    "Centering of Indigenous Voices?",
    "Centering of Indigenous Voices",
    "Level of Survivor / Relative Input?",
    "Level of Survivor / Relative Input",
    "Mechanisms for Evaluation?",
    "Mechanisms for Evaluation",
    "Prevention Efforts?",
    "Prevention Efforts",
    "Categories",
    "UIC Pros",
    "UIC Cons",
    "Validation Warnings",
)


def build_analysis_block(fields: dict) -> str:
    """Format soft Pending fields for the critic prompt."""
    lines: list[str] = []
    for key in SOFT_FIELD_NAMES:
        value = fields.get(key)
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, list):
            text = ", ".join(str(v) for v in value)
        else:
            text = str(value).strip()
        if not text:
            continue
        lines.append(f"- {key}: {text}")
    return "\n".join(lines) if lines else "(no analysis fields present)"


def build_critic_user_prompt(
    fields: dict,
    source_text: str,
    *,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
) -> str:
    excerpt = (source_text or "")[:excerpt_chars]
    return CRITIC_USER_TEMPLATE.format(
        name=str(fields.get("Name") or ""),
        state=str(fields.get("State") or ""),
        source=str(fields.get("Source") or ""),
        url=str(
            fields.get("Bill Overview (Link)")
            or fields.get("Bill Overview")
            or fields.get("Bill Text")
            or ""
        ),
        analysis_block=build_analysis_block(fields),
        excerpt=excerpt,
    )


def validate_critic_result(raw: dict) -> tuple[HallucinationCriticResult | None, list[str]]:
    try:
        return HallucinationCriticResult.model_validate(raw), []
    except Exception as exc:
        return None, [f"Schema validation failed: {exc}"]


def run_critic(
    llm,
    fields: dict,
    source_text: str,
    *,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
) -> tuple[HallucinationCriticResult | None, list[str]]:
    """Run the hallucination critic against one Pending record."""
    user = build_critic_user_prompt(fields, source_text, excerpt_chars=excerpt_chars)
    try:
        raw = llm.complete_json(CRITIC_SYSTEM, user, schema=CRITIC_SCHEMA)
    except Exception as exc:
        logger.exception("Hallucination critic LLM error: %s", exc)
        return None, [f"llm_error:{exc}"]

    result, warnings = validate_critic_result(raw)
    if result is None:
        return None, warnings
    return result, warnings
