"""Locate verbatim source spans for model-provided quote candidates."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

# Minimum similarity to accept a repaired span (anti-hallucination floor).
DEFAULT_MIN_RATIO = 0.72

_UNICODE_REPLACEMENTS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
        "\u200b": "",
        "\ufeff": "",
    }
)


def normalize_for_match(text: str) -> str:
    """Normalize text for fuzzy comparison while preserving word order."""
    cleaned = unicodedata.normalize("NFKC", text or "")
    cleaned = cleaned.translate(_UNICODE_REPLACEMENTS)
    cleaned = re.sub(r"-\s*\n\s*", "", cleaned)  # de-hyphenate line breaks
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def _token_spans(source: str) -> List[Tuple[str, int, int]]:
    return [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", source or "")]


def find_best_source_span(
    quote: str,
    source: str,
    min_ratio: float = DEFAULT_MIN_RATIO,
) -> Optional[str]:
    """
    Return the best matching verbatim substring from source for quote.
    Uses sliding windows over source word tokens; returns original casing/punctuation.
    """
    quote = (quote or "").strip()
    source = source or ""
    if not quote or not source:
        return None

    quote_norm = normalize_for_match(quote)
    if not quote_norm:
        return None

    # Fast path: already a substring after normalization mapping.
    source_norm = normalize_for_match(source)
    if quote_norm in source_norm:
        return _extract_norm_match(quote_norm, source)

    quote_words = quote_norm.split()
    if not quote_words:
        return None

    tokens = _token_spans(source)
    if not tokens:
        return None

    target_len = len(quote_words)
    # Allow slightly shorter/longer windows when PDF extraction dropped words.
    size_range = range(max(3, target_len - 3), target_len + 4)

    best_ratio = 0.0
    best_span: Optional[str] = None

    for window_size in size_range:
        if window_size > len(tokens):
            continue
        for start in range(0, len(tokens) - window_size + 1):
            window = tokens[start : start + window_size]
            window_text = " ".join(part for part, _, _ in window)
            ratio = SequenceMatcher(None, quote_norm, normalize_for_match(window_text)).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                char_start = window[0][1]
                char_end = window[-1][2]
                best_span = source[char_start:char_end]

    if best_ratio >= min_ratio and best_span:
        return best_span.strip()
    return None


def _extract_norm_match(quote_norm: str, source: str) -> Optional[str]:
    """Find a source span whose normalized form contains quote_norm."""
    tokens = _token_spans(source)
    quote_word_count = len(quote_norm.split())
    best: Optional[str] = None
    best_len = 10**9

    for window_size in range(quote_word_count, quote_word_count + 6):
        if window_size > len(tokens):
            break
        for start in range(0, len(tokens) - window_size + 1):
            window = tokens[start : start + window_size]
            window_norm = normalize_for_match(" ".join(part for part, _, _ in window))
            if quote_norm in window_norm:
                span = source[window[0][1] : window[-1][2]].strip()
                if len(span) < best_len:
                    best = span
                    best_len = len(span)
    return best


def repair_quote_list(
    quotes: List[str],
    source_text: str,
    min_ratio: float = DEFAULT_MIN_RATIO,
) -> Tuple[List[str], List[str]]:
    """
    Replace each quote with the best verbatim source span when possible.
    Returns (repaired_quotes, warnings for quotes that could not be anchored).
    """
    repaired: List[str] = []
    warnings: List[str] = []
    for i, quote in enumerate(quotes):
        quote = (quote or "").strip()
        if not quote:
            continue
        span = find_best_source_span(quote, source_text, min_ratio=min_ratio)
        if span:
            repaired.append(span)
        else:
            warnings.append(f"quote[{i}] could not be anchored in source text")
    return repaired, warnings
