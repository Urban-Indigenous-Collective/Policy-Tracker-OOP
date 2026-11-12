"""Qwen (UIC Ollama) summarization for the monthly digest overview + item blurbs."""

from __future__ import annotations

import logging
import re
from typing import Any, Sequence

from slack_client import state_display_name

logger = logging.getLogger(__name__)

_OVERVIEW_SYSTEM = (
    "You write monthly digests for the Urban Indigenous Collective "
    "MMIP Policy Tracker. Audience: advocates and community members. "
    "Tone: clear, factual, respectful. No hype, no emojis.\n\n"
    "The overview is the main value: paint the big picture of the month — "
    "trends, themes, geographic spread, counts, and what stands out. "
    "Per-item blurbs are short teasers only; readers click through for detail."
)

_OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {
            "type": "string",
            "description": (
                "3–5 short paragraphs separated by blank lines. Cover: "
                "(1) headline stats (how many new vs status moves, how many "
                "states/jurisdictions); (2) themes/trends across the updates "
                "(e.g. task forces, VAWA, forensics, DOJ partnerships); "
                "(3) anything that stands out as especially notable; "
                "(4) a one-line close pointing readers to the list below. "
                "Do not repeat full bill-by-bill narration — that belongs below."
            ),
        },
        "item_summaries": {
            "type": "object",
            "description": (
                "Map of EVERY event key → one short teaser sentence (about "
                "12–22 words). Spark curiosity; do not summarize the whole "
                "policy. No multi-sentence blurbs."
            ),
            "additionalProperties": {"type": "string"},
        },
    },
    "required": ["overview", "item_summaries"],
}

_TEASER_MAX_CHARS = 140


def _event_line(event: dict[str, Any]) -> str:
    key = str(event.get("key") or "")
    state = state_display_name(str(event.get("state") or ""))
    title = str(event.get("title") or "Policy update")
    kind = str(event.get("kind") or "")
    status = str(event.get("status") or "")
    progression = str(event.get("progression") or "")
    summary = str(event.get("summary") or "")
    bits = [f"key={key}", f"state={state}", f"title={title}", f"kind={kind}"]
    if status:
        bits.append(f"status={status}")
    if progression:
        bits.append(f"progression={progression}")
    if summary:
        bits.append(f"note={summary}")
    return " | ".join(bits)


def _teaser_from_text(text: str, *, kind: str = "") -> str:
    """Compress a long note into a short interest teaser."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        if kind == "new_live":
            return "Newly added to the tracker — open for the full entry."
        return "Updated this month — open for the full entry."
    # Prefer first sentence if it is already short enough.
    sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0].strip()
    if len(sentence) <= _TEASER_MAX_CHARS:
        return sentence
    cut = cleaned[: _TEASER_MAX_CHARS - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return f"{cut}…"


def teaser_for_event(event: dict[str, Any]) -> str:
    """Deterministic short teaser when the LLM is unavailable or incomplete."""
    kind = str(event.get("kind") or "").strip()
    note = str(event.get("summary") or "").strip()
    title = str(event.get("title") or "").strip()
    state = state_display_name(str(event.get("state") or ""))
    # Drop noisy machine notes and long pasted source text (press releases, etc.).
    note_l = note.lower()
    if note_l in {"new on the tracker", "updated in october", "updated this month"}:
        note = ""
    elif len(note) > 180 or note_l.startswith(
        ("this document", "this bill", "this act", "this resolution", "whereas")
    ):
        note = ""

    if note:
        return _teaser_from_text(note, kind=kind)

    # Title-based hook — short and clickable.
    short_title = title
    if " — " in title:
        short_title = title.split(" — ", 1)[-1].strip() or title
    short_title = short_title.rstrip(".")
    if kind == "new_live":
        hook = f"New in {state}: {short_title}." if short_title else ""
        return _teaser_from_text(hook, kind=kind)
    status = str(event.get("status") or "").strip()
    progression = str(event.get("progression") or "").strip()
    stage = progression or status
    if stage and short_title:
        return _teaser_from_text(f"{short_title} — now {stage}.", kind=kind)
    if stage:
        return _teaser_from_text(f"Status moved — now {stage}.", kind=kind)
    return _teaser_from_text("", kind=kind)


def _fallback_overview(period_label: str, events: Sequence[dict[str, Any]]) -> str:
    n = len(events)
    states = sorted(
        {
            state_display_name(str(e.get("state") or ""))
            for e in events
            if str(e.get("state") or "").strip()
        }
    )
    state_bit = ", ".join(states) if states else "multiple jurisdictions"
    new_count = sum(1 for e in events if str(e.get("kind") or "") == "new_live")
    status_count = n - new_count

    # Light theme hints from titles (deterministic, no LLM).
    blob = " ".join(str(e.get("title") or "") for e in events).lower()
    themes: list[str] = []
    theme_map = (
        ("task force", "task forces / coordinating bodies"),
        ("violence against women", "VAWA / gender-based violence"),
        ("vawa", "VAWA / gender-based violence"),
        ("forensic", "forensic / evidence process"),
        ("missing", "missing persons / MMIP response"),
        ("murder", "MMIP / homicide response"),
        ("tribal", "tribal consultation / partnership"),
        ("doj", "DOJ / federal partnership"),
        ("justice department", "DOJ / federal partnership"),
    )
    seen: set[str] = set()
    for needle, label in theme_map:
        if needle in blob and label not in seen:
            themes.append(label)
            seen.add(label)

    theme_para = (
        f"Themes that show up across this month’s list include {', '.join(themes)}."
        if themes
        else (
            "The month’s list spans several jurisdictions — scan below for what "
            "each update covers."
        )
    )

    standout = ""
    if new_count and not status_count:
        standout = (
            "What stands out: activity was entirely new publications this month "
            "(no status moves on existing Live entries)."
        )
    elif status_count and not new_count:
        standout = (
            "What stands out: no brand-new Live entries — the month was driven by "
            "status or progression changes on policies already on the tracker."
        )
    elif new_count >= status_count:
        standout = (
            "What stands out: new publications outweighed status moves, so the "
            "tracker’s footprint grew more than it churned."
        )
    else:
        standout = (
            "What stands out: status movement outpaced brand-new entries — "
            "existing Live policies carried more of the month’s change."
        )

    return (
        f"{period_label} brought {n} update{'s' if n != 1 else ''} onto the "
        f"MMIP Policy Tracker across {len(states) or 'several'} "
        f"jurisdiction{'s' if len(states) != 1 else ''}"
        f"{f' ({state_bit})' if states else ''}.\n\n"
        f"{new_count} new {'policies were' if new_count != 1 else 'policy was'} "
        f"published and {status_count} existing "
        f"{'entries' if status_count != 1 else 'entry'} moved status.\n\n"
        f"{theme_para}\n\n"
        f"{standout}\n\n"
        "Short teasers for each update are below — open any entry for the full write-up."
    )


def summarize_month(
    *,
    period_label: str,
    events: Sequence[dict[str, Any]],
) -> tuple[str, dict[str, str]]:
    """Return (overview_text, key→teaser overrides).

    Always returns a teaser for every event key. On LLM failure, uses a richer
    deterministic overview and local teasers.
    """
    if not events:
        return (
            f"{period_label} was quiet on the MMIP Policy Tracker — "
            "no new or changed Live policies were recorded.",
            {},
        )

    default_teasers = {
        str(e.get("key") or ""): teaser_for_event(e)
        for e in events
        if str(e.get("key") or "").strip()
    }

    lines = "\n".join(_event_line(e) for e in events)
    user = (
        f"Period: {period_label}\n"
        f"Event count: {len(events)}\n\n"
        "Events:\n"
        f"{lines}\n\n"
        "Write a big-picture overview (trends, themes, stats, standouts) and a "
        "short teaser for EVERY event key. Teasers must be one short sentence "
        "each — interest hooks, not full summaries."
    )
    try:
        from llm.factory import get_llm_provider

        provider = get_llm_provider()
        raw = provider.complete_json(
            _OVERVIEW_SYSTEM,
            user,
            schema=_OVERVIEW_SCHEMA,
        )
    except Exception:
        logger.exception("Monthly digest LLM overview failed; using fallback")
        return _fallback_overview(period_label, events), default_teasers

    overview = str(raw.get("overview") or "").strip()
    if not overview:
        overview = _fallback_overview(period_label, events)

    overrides = dict(default_teasers)
    item_summaries = raw.get("item_summaries")
    if isinstance(item_summaries, dict):
        for key, value in item_summaries.items():
            text = _teaser_from_text(str(value or "").strip())
            if key and text:
                overrides[str(key)] = text
    return overview, overrides
