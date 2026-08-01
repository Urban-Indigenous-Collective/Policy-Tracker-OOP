import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class EvalAnswer(str, Enum):
    YES = "Yes"
    NO = "No"
    SOMEWHAT = "Somewhat"


class BillAnalysis(BaseModel):
    summary: str = Field(..., max_length=4000)
    gender_inclusive_eval: EvalAnswer
    gender_inclusive_expl: str = ""
    mechanisms_eval: EvalAnswer
    mechanisms_expl: List[str] = Field(default_factory=list)
    prevention_efforts_eval: EvalAnswer
    prevention_efforts_expl: List[str] = Field(default_factory=list)
    centering_indigenous_voices_eval: EvalAnswer
    centering_indigenous_voices_expl: str = ""
    survivor_relative_input_eval: EvalAnswer
    survivor_relative_input_expl: str = ""
    categories: List[str] = Field(default_factory=list)

    @field_validator(
        "gender_inclusive_eval",
        "mechanisms_eval",
        "prevention_efforts_eval",
        "centering_indigenous_voices_eval",
        "survivor_relative_input_eval",
        mode="before",
    )
    @classmethod
    def normalize_eval(cls, value):
        if value is None:
            return EvalAnswer.NO
        text = str(value).strip().rstrip(".")
        lowered = text.lower()
        if lowered == "yes":
            return EvalAnswer.YES
        if lowered == "somewhat":
            return EvalAnswer.SOMEWHAT
        return EvalAnswer.NO

    @field_validator("mechanisms_expl", "prevention_efforts_expl", mode="before")
    @classmethod
    def normalize_quote_lists(cls, value):
        if value is None or value == "" or value == "No":
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        if not text or text.lower() == "no":
            return []
        parts = re.split(r"\n\s*\d+[\.\)]\s*", text)
        items = [p.strip() for p in parts if p.strip()]
        return items if len(items) > 1 else [text]

    @field_validator("categories", mode="before")
    @classmethod
    def normalize_categories(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            raw = value
        else:
            raw = [part.strip() for part in str(value).split(",")]
        return [part for part in raw if part]


class ProsConsResult(BaseModel):
    uic_pros: List[str] = Field(default_factory=list)
    uic_cons: List[str] = Field(default_factory=list)

    @field_validator("uic_pros", "uic_cons", mode="before")
    @classmethod
    def normalize_lists(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        parts = re.split(r"\n\s*\d+[\.\)]\s*", text)
        items = [p.strip() for p in parts if p.strip()]
        return items if len(items) > 1 else ([text] if text else [])


class GovMetadata(BaseModel):
    state: str
    title: str
    bill_number: str = ""
    chamber: str = "Executive"
    chamber_details: str = ""
    session_title: str = ""
    last_updated: str = ""
    sponsors_raw: str = ""

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, value):
        text = str(value or "").strip()
        if text.lower() == "national":
            return "National"
        return text.upper() if len(text) <= 3 else text
