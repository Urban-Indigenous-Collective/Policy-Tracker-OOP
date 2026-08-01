import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from analysis_schema import BillAnalysis, ProsConsResult
from analysis_validator import (
    analysis_to_compiled_fields,
    validate_bill_analysis,
    validate_gov_metadata,
    validate_pros_cons,
)
from constants import ALLOWED_CATEGORIES, PROMPT_VERSION
from titlecase import titlecase

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM = (
    "You are a precise legislative analyst for Urban Indigenous Collective. "
    "Return only valid JSON. Be accurate. Quote exact text from the legislation when asked."
)

METADATA_SYSTEM = (
    "You extract structured metadata from government documents. "
    "Return only valid JSON. Search the document text carefully."
)

PROS_CONS_SYSTEM = (
    "You summarize pros and cons of legislation for UIC. "
    "Return only valid JSON with numbered-list items as string arrays. No markdown preamble."
)

ANALYSIS_SCHEMA = {
    "summary": "string, max 5 sentences",
    "gender_inclusive_eval": "Yes | No | Somewhat",
    "gender_inclusive_expl": "string",
    "mechanisms_eval": "Yes | No",
    "mechanisms_expl": ["exact quotes from bill when Yes, else []"],
    "prevention_efforts_eval": "Yes | No",
    "prevention_efforts_expl": ["exact quotes from bill when Yes, else []"],
    "centering_indigenous_voices_eval": "Yes | No | Somewhat",
    "centering_indigenous_voices_expl": "string",
    "survivor_relative_input_eval": "Yes | No | Somewhat",
    "survivor_relative_input_expl": "string",
    "categories": ALLOWED_CATEGORIES,
}

METADATA_SCHEMA = {
    "state": "state initials e.g. NY, CT, or National",
    "title": "exact document title from source",
    "bill_number": "formatted e.g. EO14053, DOJ24-570, or empty",
    "chamber": "Executive, House, Senate, or department name",
    "chamber_details": "date and action string",
    "session_title": "administration or session label",
    "last_updated": "YYYY-MM-DD",
    "sponsors_raw": "comma-separated sponsor list",
}


class BillAnalyzer:
    def __init__(self, llm_provider, cache_dir=None):
        self.llm = llm_provider
        self.cache_dir = Path(cache_dir or os.getenv("LLM_CACHE_DIR", "cache"))
        self.cache_enabled = os.getenv("LLM_CACHE_ENABLED", "true").lower() in ("1", "true", "yes")
        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, kind: str, *parts: str) -> str:
        raw = "|".join([PROMPT_VERSION, self.llm.model, kind, *parts])
        return hashlib.sha256(raw.encode()).hexdigest()

    def _read_cache(self, key: str) -> Optional[dict]:
        if not self.cache_enabled:
            return None
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            logger.info("cache_hit key=%s", key[:12])
            return json.loads(path.read_text())
        return None

    def _write_cache(self, key: str, data: dict):
        if not self.cache_enabled:
            return
        path = self.cache_dir / f"{key}.json"
        path.write_text(json.dumps(data, indent=2))

    def _complete_json_with_retry(
        self,
        kind: str,
        cache_parts: tuple[str, ...],
        system: str,
        user: str,
        schema: dict,
        validator,
        source_text: str = "",
    ):
        cache_key = self._cache_key(kind, *cache_parts)
        cached = self._read_cache(cache_key)
        if cached is not None:
            validated, warnings = validator(cached, source_text) if source_text else validator(cached)
            if validated is not None:
                return validated, warnings, True

        raw = self.llm.complete_json(system, user, schema=schema)
        validated, warnings = validator(raw, source_text) if source_text else validator(raw)

        if validated is None and warnings:
            retry_user = user + "\n\nFix these validation errors:\n" + "\n".join(warnings)
            logger.warning("validation_retry kind=%s errors=%s", kind, warnings)
            raw = self.llm.complete_json(system, retry_user, schema=schema)
            validated, warnings = validator(raw, source_text) if source_text else validator(raw)

        if validated is not None:
            self._write_cache(cache_key, raw if isinstance(raw, dict) else validated.model_dump())

        return validated, warnings, False

    def extract_gov_metadata(self, bill_text: str, bill_link: str):
        user = (
            f"Document URL: {bill_link}\n\n"
            f"Document text:\n{bill_text}\n\n"
            "Extract metadata fields from this document."
        )
        metadata, warnings, _ = self._complete_json_with_retry(
            "gov_metadata",
            (bill_link,),
            METADATA_SYSTEM,
            user,
            METADATA_SCHEMA,
            lambda data, _="": validate_gov_metadata(data),
        )
        if metadata is None:
            raise ValueError(f"Failed to extract metadata: {'; '.join(warnings)}")
        metadata.title = titlecase(metadata.title)
        return metadata, warnings

    def analyze_bill(self, bill_text: str, indigenous_sponsors: str, progress_callback: Optional[Callable] = None):
        if progress_callback:
            progress_callback("analysis", 0.5)

        user = (
            f"Indigenous sponsors (if any): {indigenous_sponsors or 'None identified'}\n\n"
            f"Legislation text:\n{bill_text}\n\n"
            "Analyze this legislation for UIC. "
            "For eval fields use exactly Yes, No, or Somewhat. "
            "When eval is No, set expl to the literal string No. "
            "For quote lists, include only exact substrings from the legislation."
        )

        analysis, warnings, cache_hit = self._complete_json_with_retry(
            "bill_analysis",
            (hashlib.sha256(bill_text.encode()).hexdigest()[:16], indigenous_sponsors),
            ANALYSIS_SYSTEM,
            user,
            ANALYSIS_SCHEMA,
            validate_bill_analysis,
            bill_text,
        )
        logger.info(
            "analyze_bill cache_hit=%s warnings=%s",
            cache_hit,
            warnings,
        )
        if analysis is None:
            raise ValueError(f"Failed to analyze bill: {'; '.join(warnings)}")
        return analysis, warnings

    def pros_and_cons(
        self,
        analysis: BillAnalysis,
        indigenous_sponsors: str,
        progress_callback: Optional[Callable] = None,
    ):
        if progress_callback:
            progress_callback("pros_cons", 0.85)

        data_points = {
            "summary": analysis.summary,
            "gender_inclusive_eval": analysis.gender_inclusive_eval.value,
            "gender_inclusive_expl": analysis.gender_inclusive_expl,
            "mechanisms_eval": analysis.mechanisms_eval.value,
            "mechanisms_expl": analysis.mechanisms_expl,
            "prevention_efforts_eval": analysis.prevention_efforts_eval.value,
            "prevention_efforts_expl": analysis.prevention_efforts_expl,
            "indigenous_sponsors": indigenous_sponsors,
            "centering_indigenous_voices_eval": analysis.centering_indigenous_voices_eval.value,
            "centering_indigenous_voices_expl": analysis.centering_indigenous_voices_expl,
            "survivor_relative_input_eval": analysis.survivor_relative_input_eval.value,
            "survivor_relative_input_expl": analysis.survivor_relative_input_expl,
            "categories": analysis.categories,
        }

        user = (
            "Using these validated analysis data points, list pros and cons.\n"
            f"{json.dumps(data_points, indent=2)}"
        )

        pros_cons, warnings, _ = self._complete_json_with_retry(
            "pros_cons",
            (hashlib.sha256(json.dumps(data_points, sort_keys=True).encode()).hexdigest()[:16],),
            PROS_CONS_SYSTEM,
            user,
            {"uic_pros": ["string"], "uic_cons": ["string"]},
            lambda data, _="": validate_pros_cons(data),
        )
        if pros_cons is None:
            raise ValueError(f"Failed to generate pros/cons: {'; '.join(warnings)}")
        return pros_cons, warnings

    def run_full_analysis(
        self,
        bill_text: str,
        indigenous_sponsors: str,
        progress_callback: Optional[Callable] = None,
    ) -> dict:
        analysis, analysis_warnings = self.analyze_bill(
            bill_text, indigenous_sponsors, progress_callback
        )
        pros_cons, pros_warnings = self.pros_and_cons(
            analysis, indigenous_sponsors, progress_callback
        )
        all_warnings = analysis_warnings + pros_warnings
        return analysis_to_compiled_fields(analysis, pros_cons, all_warnings)
