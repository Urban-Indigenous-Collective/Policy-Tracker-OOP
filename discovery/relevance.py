import hashlib
import logging
import os
from typing import Optional

from analysis_schema import MMIPRelevanceResult
from analysis_validator import validate_mmip_relevance
from discovery.models import Candidate
from discovery.queries import keyword_prescreen

logger = logging.getLogger(__name__)

RELEVANCE_SYSTEM = (
    "You are a legislative screening assistant for Urban Indigenous Collective (UIC). "
    "Determine whether a document specifically addresses Missing and Murdered Indigenous Peoples (MMIP). "
    "Return only valid JSON."
)

RELEVANCE_SCHEMA = {
    "is_mmip": "boolean — true only if the document specifically addresses MMIP",
    "confidence": "float 0.0-1.0",
    "rationale": "brief explanation of why it is or is not MMIP-related",
    "primary_subject": "one-line description of the document's main subject",
}

RELEVANCE_USER_TEMPLATE = """Title: {title}
State: {state}
Source URL: {url}

Document excerpt:
{excerpt}

MMIP relevance criteria:
- RELEVANT: legislation or executive orders specifically addressing missing or murdered Indigenous people,
  Native American/Alaska Native/Native Hawaiian missing persons, tribal MMIP task forces, MMIW/MMIP data
  collection, Savanna's Act, Not Invisible Act, or similar Indigenous-specific missing/murdered persons policy.
- NOT RELEVANT: general missing-persons legislation, AMBER Alert bills, human trafficking bills with no
  Indigenous nexus, tribal gaming/compacts, general criminal justice bills, or legislation about missing
  persons that does not specifically address Indigenous communities.

Decide if this document is MMIP-relevant for UIC's policy tracker."""


class MMIPRelevanceGate:
    """Two-stage MMIP relevance filter: keyword prescreen + LLM adjudication."""

    def __init__(self, llm_provider, min_confidence: float | None = None):
        self.llm = llm_provider
        self.min_confidence = min_confidence or float(
            os.getenv("DISCOVERY_RELEVANCE_MIN_CONFIDENCE", "0.6")
        )

    def prescreen(self, candidate: Candidate) -> bool:
        combined = f"{candidate.title}\n{candidate.snippet}"
        return keyword_prescreen(combined)

    def evaluate(
        self,
        candidate: Candidate,
        excerpt: str = "",
    ) -> tuple[bool, MMIPRelevanceResult | None, str]:
        """
        Return (is_relevant, result, stage).
        stage is 'prescreen_fail', 'llm', or 'confidence_fail'.
        """
        if not self.prescreen(candidate):
            return False, None, "prescreen_fail"

        text = excerpt or candidate.snippet or candidate.title
        excerpt_trimmed = text[:4000]

        user = RELEVANCE_USER_TEMPLATE.format(
            title=candidate.title,
            state=candidate.state,
            url=candidate.url,
            excerpt=excerpt_trimmed,
        )

        try:
            raw = self.llm.complete_json(RELEVANCE_SYSTEM, user, schema=RELEVANCE_SCHEMA)
            result, warnings = validate_mmip_relevance(raw)
            if result is None:
                logger.warning("MMIP relevance validation failed: %s", warnings)
                return False, None, "llm_fail"

            if not result.is_mmip:
                return False, result, "llm"
            if result.confidence < self.min_confidence:
                return False, result, "confidence_fail"
            return True, result, "llm"
        except Exception as exc:
            logger.exception("MMIP relevance LLM error: %s", exc)
            return False, None, "llm_error"

    @staticmethod
    def cache_key(candidate: Candidate, excerpt: str) -> str:
        raw = f"{candidate.url}|{candidate.title}|{excerpt[:4000]}"
        return hashlib.sha256(raw.encode()).hexdigest()
