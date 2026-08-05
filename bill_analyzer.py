import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from analysis_schema import BillAnalysis, EvalAnswer, ProsConsResult
from analysis_validator import (
    analysis_to_compiled_fields,
    validate_bill_analysis,
    validate_gov_metadata,
    validate_pros_cons,
)
from constants import ALLOWED_CATEGORIES, PROMPT_VERSION
from processing_log import log as plog
from titlecase import titlecase

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM = (
    "You are a precise legislative analyst for Urban Indigenous Collective. "
    "Return only valid JSON. Be accurate. "
    "For mechanisms_expl and prevention_efforts_expl you MUST copy verbatim substrings "
    "from the legislation — do not paraphrase, summarize, or normalize punctuation."
)

QUOTE_EXTRACT_SYSTEM = (
    "You extract verbatim supporting quotes from legislation. "
    "Return only valid JSON. Each quote must be copied character-for-character from the "
    "provided legislation text — never paraphrase."
)

METADATA_SYSTEM = (
    "You extract structured metadata from government documents. "
    "Return only valid JSON. Use ONLY facts explicitly stated in the document text. "
    "If the date, sponsor, chamber action, or session/administration is not stated "
    "in the text, return an empty string for that field. Do not infer governors, "
    "proclamations, or annual observance dates from the title or URL alone."
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
    "mechanisms_expl": ["verbatim copy-paste substrings from legislation when Yes, else []"],
    "prevention_efforts_eval": "Yes | No",
    "prevention_efforts_expl": ["verbatim copy-paste substrings from legislation when Yes, else []"],
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

    def _cache_key(self, kind: str, *parts) -> str:
        str_parts = []
        for part in parts:
            if isinstance(part, (list, dict)):
                str_parts.append(json.dumps(part, sort_keys=True))
            else:
                str_parts.append(str(part))
        raw = "|".join([PROMPT_VERSION, self.llm.model, kind, *str_parts])
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

    def _quote_warning_items(self, warnings: list[str]) -> list[str]:
        return [
            w
            for w in warnings
            if "quote not found" in w or "could not be anchored" in w
        ]

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
            plog("Using cached LLM result")
            validated, warnings = validator(cached, source_text) if source_text else validator(cached)
            if validated is not None:
                return validated, warnings, True

        plog(f"LLM request: {kind}")
        raw = self._complete_json_with_retry_body(
            kind, system, user, schema, validator, source_text
        )
        validated, warnings = validator(raw, source_text) if source_text else validator(raw)

        if validated is not None:
            self._write_cache(cache_key, raw if isinstance(raw, dict) else validated.model_dump())

        return validated, warnings, False

    def _complete_json_with_retry_body(
        self,
        kind: str,
        system: str,
        user: str,
        schema: dict,
        validator,
        source_text: str = "",
    ) -> dict:
        raw = self.llm.complete_json(system, user, schema=schema)
        plog(f"LLM response received: {kind}")
        validated, warnings = validator(raw, source_text) if source_text else validator(raw)

        if validated is None and warnings:
            retry_user = user + "\n\nFix these validation errors:\n" + "\n".join(warnings)
            logger.warning("validation_retry kind=%s errors=%s", kind, warnings)
            raw = self.llm.complete_json(system, retry_user, schema=schema)
            validated, warnings = validator(raw, source_text) if source_text else validator(raw)

        quote_warnings = self._quote_warning_items(warnings)
        if validated is not None and quote_warnings and source_text:
            retry_user = (
                user
                + "\n\nYour supporting quotes were not verbatim copies from the legislation. "
                "Re-read the legislation text and fix ONLY the quote list fields. "
                "Each quote must appear exactly in the text (copy-paste, no paraphrase).\n"
                "Issues:\n"
                + "\n".join(quote_warnings)
            )
            logger.warning("quote_validation_retry kind=%s errors=%s", kind, quote_warnings)
            raw = self.llm.complete_json(system, retry_user, schema=schema)
            validated, warnings = validator(raw, source_text)
            if validated is None:
                return raw

        return raw if isinstance(raw, dict) else (validated.model_dump() if validated else raw)

    def _extract_verbatim_quotes(
        self,
        bill_text: str,
        question: str,
        cache_suffix: str,
    ) -> list[str]:
        user = (
            f"Legislation text:\n{bill_text}\n\n"
            f"Question: {question}\n"
            "If Yes, return JSON {\"quotes\": [\"verbatim substring\", ...]} using only exact "
            "copy-paste from the legislation above. If No supporting language exists, "
            "return {\"quotes\": []}."
        )
        raw = self.llm.complete_json(
            QUOTE_EXTRACT_SYSTEM,
            user,
            schema={"quotes": ["verbatim substring from legislation"]},
        )
        quotes = raw.get("quotes") if isinstance(raw, dict) else []
        if not isinstance(quotes, list):
            return []
        from quote_repair import repair_quote_list

        repaired, _ = repair_quote_list([str(q).strip() for q in quotes if str(q).strip()], bill_text)
        logger.info("verbatim_quote_extract suffix=%s count=%d", cache_suffix, len(repaired))
        return repaired

    def extract_gov_metadata(self, bill_text: str, bill_link: str):
        text_hash = hashlib.sha256(bill_text.encode()).hexdigest()[:16]
        user = (
            f"Document URL: {bill_link}\n\n"
            f"Document text:\n{bill_text}\n\n"
            "Extract metadata fields from this document. "
            "Use only facts explicitly present in the document text above."
        )
        metadata, warnings, _ = self._complete_json_with_retry(
            "gov_metadata",
            (bill_link, text_hash),
            METADATA_SYSTEM,
            user,
            METADATA_SCHEMA,
            lambda data, _="": validate_gov_metadata(data),
        )
        if metadata is None:
            raise ValueError(f"Failed to extract metadata: {'; '.join(warnings)}")
        metadata.title = titlecase(metadata.title)
        return metadata, warnings

    def analyze_bill(self, bill_text: str, indigenous_sponsors, progress_callback: Optional[Callable] = None):
        if isinstance(indigenous_sponsors, list):
            indigenous_sponsors = ", ".join(indigenous_sponsors)
        if progress_callback:
            progress_callback("analysis", 0.1)
        plog("Starting structured bill analysis")

        user = (
            f"Indigenous sponsors (if any): {indigenous_sponsors or 'None identified'}\n\n"
            f"Legislation text:\n{bill_text}\n\n"
            "Analyze this legislation for UIC. "
            "For eval fields use exactly Yes, No, or Somewhat. "
            "When eval is No or Somewhat, set gender_inclusive_expl, centering_indigenous_voices_expl, "
            "and survivor_relative_input_expl to the literal string No or Somewhat respectively. "
            "When mechanisms_eval or prevention_efforts_eval is No, set mechanisms_expl and "
            "prevention_efforts_expl to empty arrays []. "
            "When mechanisms_eval or prevention_efforts_eval is Yes, each expl entry must be a "
            "verbatim copy-paste substring from the legislation above — not a summary."
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

        if analysis and self._quote_warning_items(warnings):
            if analysis.mechanisms_eval == EvalAnswer.YES and any(
                w.startswith("mechanisms_expl") for w in warnings
            ):
                analysis.mechanisms_expl = self._extract_verbatim_quotes(
                    bill_text,
                    "Does this legislation include accountability mechanisms, reporting requirements, "
                    "oversight, audits, or evaluation processes related to MMIP?",
                    "mechanisms",
                )
            if analysis.prevention_efforts_eval == EvalAnswer.YES and any(
                w.startswith("prevention_efforts_expl") for w in warnings
            ):
                analysis.prevention_efforts_expl = self._extract_verbatim_quotes(
                    bill_text,
                    "Does this legislation include prevention efforts related to MMIP "
                    "(training, education, outreach, intervention programs)?",
                    "prevention",
                )
            analysis, warnings = validate_bill_analysis(analysis.model_dump(), bill_text)
        logger.info(
            "analyze_bill cache_hit=%s warnings=%s",
            cache_hit,
            warnings,
        )
        if analysis is None:
            raise ValueError(f"Failed to analyze bill: {'; '.join(warnings)}")
        if progress_callback:
            progress_callback("analysis", 1.0)
        plog("Bill analysis validated")
        return analysis, warnings

    def pros_and_cons(
        self,
        analysis: BillAnalysis,
        indigenous_sponsors,
        progress_callback: Optional[Callable] = None,
    ):
        if isinstance(indigenous_sponsors, list):
            indigenous_sponsors = ", ".join(indigenous_sponsors)
        if progress_callback:
            progress_callback("pros_cons", 0.1)
        plog("Generating UIC pros and cons")

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
        if progress_callback:
            progress_callback("pros_cons", 1.0)
        plog("Pros and cons complete")
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
