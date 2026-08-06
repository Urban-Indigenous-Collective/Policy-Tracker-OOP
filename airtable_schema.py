"""Airtable field definitions shared between Pending (mirrors Main v3) and setup scripts."""

from constants import ALLOWED_CATEGORIES

# Legislative status — matches Main v3
STATUS_CHOICES = ["Pending", "Passed", "Failed"]

# LegiScan progression codes — matches Main v3
PROGRESSION_CHOICES = [
    "Pre-filed or pre-introduction",
    "Introduced",
    "Engrossed",
    "Enrolled",
    "Passed",
    "Vetoed",
    "Failed Limited support based on state",
    "Override Progress",
    "Chaptered Progress",
    "Refer Progress",
    "Report Pass Progress",
    "Report DNP Progress",
    "Draft Progress",
    "Progression",
]

CHAMBER_CHOICES = ["Executive", "Senate", "House"]

EVAL_TBD_FIELDS = {
    "Mechanisms for Evaluation?",
    "Gender Inclusive Language?",
    "Prevention Efforts?",
}

EVAL_YES_NO_SOMEWHAT_FIELDS = {
    "Level of Survivor / Relative Input?",
    "Centering of Indigenous Voices?",
}

# Main v3 includes a stray "Categories" tag option alongside real categories
CATEGORY_CHOICES = ALLOWED_CATEGORIES + ["Categories"]

PENDING_REVIEW_STATUS_CHOICES = ["Pending Review", "Approved", "Rejected"]
LIVE_REVIEW_STATUS_CHOICES = ["Live", "Send Back to Pending"]
# Pending-only workflow field (not on Main v3). Federal Site tracks DOJ/USAO/FR crawls.
SOURCE_CHOICES = ["LegiScan", "State Site", "Federal Site"]

# Fields mirrored from Main v3 (excludes Created By and table-specific Review Status values)
BILL_FIELD_NAMES = [
    "State",
    "Name",
    "Bill Number",
    "Status",
    "Progression",
    "Chamber",
    "Chamber Details",
    "Bill Overview (Link)",
    "Bill Text",
    "Optional Link",
    "Summary",
    "UIC Pros",
    "UIC Cons",
    "Mechanisms for Evaluation?",
    "Mechanisms for Evaluation",
    "Gender Inclusive Language?",
    "Gender Inclusive Language",
    "Prevention Efforts?",
    "Prevention Efforts",
    "Level of Survivor / Relative Input?",
    "Level of Survivor / Relative Input",
    "Centering of Indigenous Voices?",
    "Centering of Indigenous Voices",
    "Sponsors of the Legislation",
    "Indigenous Sponsorship",
    "Session",
    "Categories",
    "Last Update",
]

PENDING_ONLY_FIELD_NAMES = [
    "Review Status",
    "Source",
    "Discovered On",
]

# Discovery metadata — on Pending and Main v3 (carried over on approve)
DISCOVERY_METADATA_FIELD_NAMES = [
    "Validation Warnings",
    "Relevance Confidence",
    "Relevance Rationale",
]

# Legacy Pending field names → Main v3 names (for migration)
LEGACY_FIELD_RENAMES = {
    "Title": "Name",
    "Bill Overview": "Bill Overview (Link)",
    "Gender Inclusive Explanation": "Gender Inclusive Language",
    "Sponsors": "Sponsors of the Legislation",
}


def _choices(names: list[str]) -> dict:
    return {"choices": [{"name": n} for n in names]}


def _single_select(names: list[str]) -> dict:
    return {"type": "singleSelect", "options": _choices(names)}


def _multiple_select(names: list[str]) -> dict:
    return {"type": "multipleSelects", "options": _choices(names)}


def bill_field_defs() -> list[dict]:
    """Field definitions for Pending bill columns — mirrors Main v3 types/options."""
    return [
        {"name": "State", "type": "singleLineText"},
        {"name": "Name", "type": "multilineText"},
        {"name": "Bill Number", "type": "singleLineText"},
        {"name": "Status", **_single_select(STATUS_CHOICES)},
        {"name": "Progression", **_single_select(PROGRESSION_CHOICES)},
        {"name": "Chamber", **_single_select(CHAMBER_CHOICES)},
        {"name": "Chamber Details", "type": "multilineText"},
        {"name": "Bill Overview (Link)", "type": "url"},
        {"name": "Bill Text", "type": "url"},
        {"name": "Optional Link", "type": "url"},
        {"name": "Summary", "type": "multilineText"},
        {"name": "UIC Pros", "type": "multilineText"},
        {"name": "UIC Cons", "type": "multilineText"},
        {"name": "Mechanisms for Evaluation?", **_single_select(["No", "TBD or TCRP Specific", "Yes"])},
        {"name": "Mechanisms for Evaluation", "type": "multilineText"},
        {"name": "Gender Inclusive Language?", **_single_select(["No", "Yes", "TBD or TCRP Specific"])},
        {"name": "Gender Inclusive Language", "type": "multilineText"},
        {"name": "Prevention Efforts?", **_single_select(["No", "TBD or TCRP Specific", "Yes"])},
        {"name": "Prevention Efforts", "type": "multilineText"},
        {"name": "Level of Survivor / Relative Input?", **_single_select(["Yes", "Somewhat", "No"])},
        {"name": "Level of Survivor / Relative Input", "type": "multilineText"},
        {"name": "Centering of Indigenous Voices?", **_single_select(["Yes", "Somewhat", "No"])},
        {"name": "Centering of Indigenous Voices", "type": "multilineText"},
        {"name": "Sponsors of the Legislation", "type": "multilineText"},
        {"name": "Indigenous Sponsorship", "type": "multilineText"},
        {"name": "Session", "type": "singleLineText"},
        {"name": "Categories", **_multiple_select(CATEGORY_CHOICES)},
        {"name": "Last Update", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
    ]


def discovery_metadata_field_defs() -> list[dict]:
    """Fields preserved on both Pending and Main v3."""
    return [
        {"name": "Validation Warnings", "type": "multilineText"},
        {"name": "Relevance Confidence", "type": "number", "options": {"precision": 2}},
        {"name": "Relevance Rationale", "type": "multilineText"},
    ]


def pending_workflow_field_defs() -> list[dict]:
    """Pending-only workflow fields — Review Status is cloned from Main v3 with different options."""
    return [
        {"name": "Source", **_single_select(SOURCE_CHOICES)},
        {"name": "Discovered On", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
    ]


def pending_field_defs() -> list[dict]:
    return bill_field_defs() + discovery_metadata_field_defs() + pending_workflow_field_defs()
