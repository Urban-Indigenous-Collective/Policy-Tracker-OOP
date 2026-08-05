"""Adjudicate mechanisms/prevention eval↔expl contradictions.

When eval≠Yes but expl has quotes (or vice versa), decide which side is wrong
using document-type classification and rubric-grounded quote analysis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List

from analysis_schema import BillAnalysis, EvalAnswer
from quote_repair import find_best_source_span, normalize_for_match


PDF_JUNK = re.compile(r"E:\\BILLS\\|pamtmann|DSK\w+PROD|Sfmt \d+", re.I)
PROC_PATTERN = re.compile(
    r"(?i)(proclamation|awareness day|by the president|executive order|"
    r"whereas|resolved|urges congress|memorializing|honoring the lives)",
)
BILL_PATTERN = re.compile(
    r"(?i)(be it enacted|an act relating|section \d+|shall be codified|"
    r"new section|amended to read|insert the following)",
)
MECH_PATTERNS = re.compile(
    r"(?i)(shall (?:establish|create|implement|submit|report|maintain|develop)|"
    r"annual report|task force|oversight|audit|accountability|repository|"
    r"office of liaison|coordinator|data (?:system|repository|collection))",
)
PREV_PATTERNS = re.compile(
    r"(?i)(training|education|outreach|prevention program|awareness|intervention|"
    r"minimum of \d+ hours|develop and implement)",
)


def quote_in_source(quote: str, source_text: str) -> bool:
    quote_norm = normalize_for_match(quote)
    source_norm = normalize_for_match(source_text)
    if not quote_norm:
        return True
    if quote_norm in source_norm:
        return True
    if len(quote_norm) < 20:
        return quote_norm in source_norm
    words = quote_norm.split()
    window = " ".join(words[: min(len(words), 12)])
    if window in source_norm or quote_norm[:120] in source_norm:
        return True
    return find_best_source_span(quote, source_text) is not None


class AdjudicationAction(str, Enum):
    NONE = "none"
    CLEAR_EXPL = "clear_expl"
    FLIP_EVAL_YES = "flip_eval_yes"
    REVIEW = "review"


@dataclass
class FieldAdjudication:
    field: str
    action: AdjudicationAction
    who_wrong: str
    reason: str
    expl_status: str = ""


@dataclass
class EvalExplAdjudication:
    document_type: str = "unknown"
    mech: FieldAdjudication | None = None
    prev: FieldAdjudication | None = None
    has_contradiction: bool = False


def classify_doc_type(name: str, source_text: str, url: str) -> str:
    text_head = source_text[:3000]
    if PROC_PATTERN.search(text_head) and not BILL_PATTERN.search(text_head):
        if "proclamation" in text_head.lower() or "awareness day" in name.lower():
            return "proclamation"
        if "resolved" in text_head.lower() or re.search(r"\bSR\d|\bHR\d|\bACR", name):
            return "resolution"
        return "proclamation/commemorative"
    if BILL_PATTERN.search(source_text[:8000]):
        return "bill"
    if "press release" in text_head.lower() or "/pr/" in url:
        return "press_release"
    if PDF_JUNK.search(source_text[:500]):
        return "bill"
    return "unknown"


def quote_establishes(quote: str, doc_type: str) -> tuple[bool, bool]:
    """Return (establishes_obligation, mentions_existing_only)."""
    q = quote.lower()
    establishes = bool(
        re.search(
            r"shall (establish|create|implement|develop|submit|maintain|report|appoint)",
            q,
        )
        or re.search(r"(is created|are created|must develop|directs the)", q)
        or re.search(r"annual report", q)
    )
    mentions_only = bool(
        re.search(r"(has developed|has launched|currently|we are|created a new unit)", q)
        or re.search(r"(investing in|expanding funding)", q)
    )
    if doc_type in ("proclamation", "proclamation/commemorative", "resolution"):
        if not establishes and (
            "training" in q or "report" in q or "coordinator" in q or "office" in q
        ):
            mentions_only = True
    return establishes, mentions_only


def _action_from_adjudication(
    who_wrong: str,
    expl_status: str,
    eval_val: EvalAnswer,
) -> AdjudicationAction:
    if who_wrong == "neither":
        return AdjudicationAction.NONE
    if who_wrong == "expl":
        if expl_status in (
            "header_junk",
            "quotes_exist_eval_no",
            "hallucinated_or_unanchored",
        ):
            return AdjudicationAction.CLEAR_EXPL
        return AdjudicationAction.REVIEW
    if who_wrong == "eval" and expl_status == "quotes_support_yes":
        if eval_val != EvalAnswer.YES:
            return AdjudicationAction.FLIP_EVAL_YES
        return AdjudicationAction.NONE
    if who_wrong == "both":
        return AdjudicationAction.REVIEW
    return AdjudicationAction.REVIEW


def adjudicate_field(
    eval_val: EvalAnswer,
    quotes: List[str],
    doc_type: str,
    field: str,
    source_text: str,
) -> FieldAdjudication | None:
    if eval_val == EvalAnswer.YES and quotes:
        return None
    if eval_val == EvalAnswer.YES and not quotes:
        return FieldAdjudication(
            field=field,
            action=AdjudicationAction.REVIEW,
            who_wrong="eval",
            reason="eval=Yes but no supporting quotes",
            expl_status="missing_quotes",
        )
    if eval_val != EvalAnswer.YES and not quotes:
        return None

    has_junk = any(PDF_JUNK.search(q) for q in quotes)
    if has_junk:
        return FieldAdjudication(
            field=field,
            action=AdjudicationAction.CLEAR_EXPL,
            who_wrong="expl",
            reason="PDF header/footer lines quoted as content",
            expl_status="header_junk",
        )

    grounded = all(quote_in_source(q, source_text) for q in quotes)
    if not grounded:
        return FieldAdjudication(
            field=field,
            action=AdjudicationAction.CLEAR_EXPL,
            who_wrong="expl",
            reason="Quotes not grounded in source text",
            expl_status="hallucinated_or_unanchored",
        )

    establishes_any = False
    mentions_any = False
    for q in quotes[:5]:
        est, ment = quote_establishes(q, doc_type)
        establishes_any = establishes_any or est
        mentions_any = mentions_any or ment

    patterns = MECH_PATTERNS if field == "mech" else PREV_PATTERNS
    pattern_hit = any(patterns.search(q) for q in quotes)

    who_wrong = "neither"
    expl_status = "quotes_support_yes"
    reason = ""

    if doc_type in ("proclamation", "proclamation/commemorative", "resolution"):
        if mentions_any and not establishes_any:
            who_wrong = "expl"
            expl_status = "quotes_exist_eval_no"
            reason = "Non-binding doc cites existing programs, does not establish obligations"
        elif establishes_any and eval_val != EvalAnswer.YES:
            who_wrong = "eval"
            reason = "Binding language found but eval≠Yes"
        elif pattern_hit and not establishes_any and eval_val == EvalAnswer.NO:
            who_wrong = "expl"
            expl_status = "quotes_exist_eval_no"
            reason = f"{doc_type} mentions programs aspirationally, not establishing them"
    elif establishes_any or (pattern_hit and doc_type == "bill"):
        if eval_val != EvalAnswer.YES:
            who_wrong = "eval"
            reason = "Bill text establishes obligations; eval under-called"
    elif pattern_hit and eval_val == EvalAnswer.NO:
        if field == "prev" and any("training" in q.lower() for q in quotes):
            who_wrong = "eval"
            reason = "Training mandate in bill; eval under-called"
        else:
            who_wrong = "both"
            expl_status = "quotes_exist_eval_no"
            reason = "Quotes mention related concepts but obligation unclear"
    elif eval_val != EvalAnswer.YES:
        who_wrong = "expl"
        expl_status = "quotes_exist_eval_no"
        reason = "Quotes don't meet rubric threshold"

    action = _action_from_adjudication(who_wrong, expl_status, eval_val)
    return FieldAdjudication(
        field=field,
        action=action,
        who_wrong=who_wrong,
        reason=reason,
        expl_status=expl_status,
    )


def adjudicate_eval_expl(
    analysis: BillAnalysis,
    source_text: str,
    *,
    name: str = "",
    url: str = "",
) -> EvalExplAdjudication:
    doc_type = classify_doc_type(name, source_text, url)
    result = EvalExplAdjudication(document_type=doc_type)

    mech = adjudicate_field(
        analysis.mechanisms_eval,
        analysis.mechanisms_expl,
        doc_type,
        "mech",
        source_text,
    )
    prev = adjudicate_field(
        analysis.prevention_efforts_eval,
        analysis.prevention_efforts_expl,
        doc_type,
        "prev",
        source_text,
    )

    result.mech = mech
    result.prev = prev
    result.has_contradiction = bool(
        (mech and mech.action != AdjudicationAction.NONE)
        or (prev and prev.action != AdjudicationAction.NONE)
    )
    return result


def apply_safe_fixes(
    analysis: BillAnalysis,
    adjudication: EvalExplAdjudication,
) -> List[str]:
    """Apply tier-1/2 auto-fixes (clear expl, flip eval). Returns descriptions."""
    applied: List[str] = []

    for adj in (adjudication.mech, adjudication.prev):
        if adj is None or adj.action == AdjudicationAction.NONE:
            continue
        if adj.action == AdjudicationAction.REVIEW:
            continue

        if adj.field == "mech":
            if adj.action == AdjudicationAction.CLEAR_EXPL:
                analysis.mechanisms_expl = []
                applied.append(f"mechanisms: cleared expl ({adj.reason})")
            elif adj.action == AdjudicationAction.FLIP_EVAL_YES:
                analysis.mechanisms_eval = EvalAnswer.YES
                applied.append(f"mechanisms: flipped eval to Yes ({adj.reason})")
        elif adj.field == "prev":
            if adj.action == AdjudicationAction.CLEAR_EXPL:
                analysis.prevention_efforts_expl = []
                applied.append(f"prevention: cleared expl ({adj.reason})")
            elif adj.action == AdjudicationAction.FLIP_EVAL_YES:
                analysis.prevention_efforts_eval = EvalAnswer.YES
                applied.append(f"prevention: flipped eval to Yes ({adj.reason})")

    return applied


def is_safe_auto_fix(action: AdjudicationAction) -> bool:
    return action in (AdjudicationAction.CLEAR_EXPL, AdjudicationAction.FLIP_EVAL_YES)
