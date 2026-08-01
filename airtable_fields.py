"""Airtable field names shared between Pending and Main v3 tables."""

# Columns produced by bill_processor.parse_bill_object()
BILL_FIELD_NAMES = [
    "State",
    "Title",
    "Bill Number",
    "Status",
    "Progression",
    "Chamber",
    "Chamber Details",
    "Bill Overview",
    "Bill Text",
    "Optional Link",
    "Summary",
    "UIC Pros",
    "UIC Cons",
    "Mechanisms for Evaluation?",
    "Mechanisms for Evaluation",
    "Gender Inclusive Language?",
    "Gender Inclusive Explanation",
    "Prevention Efforts?",
    "Prevention Efforts",
    "Level of Survivor / Relative Input?",
    "Level of Survivor / Relative Input",
    "Centering of Indigenous Voices?",
    "Centering of Indigenous Voices",
    "Sponsors",
    "Indigenous Sponsorship",
    "Session",
    "Categories",
    "Last Update",
    "Validation Warnings",
]

# Pending-only fields
PENDING_EXTRA_FIELDS = [
    "Review Status",
    "Source",
    "Relevance Confidence",
    "Relevance Rationale",
    "Discovered On",
]

# Main v3 review field
LIVE_REVIEW_STATUS_FIELD = "Review Status"

REVIEW_STATUS_PENDING = "Pending Review"
REVIEW_STATUS_APPROVED = "Approved"
REVIEW_STATUS_REJECTED = "Rejected"
REVIEW_STATUS_LIVE = "Live"
REVIEW_STATUS_SEND_BACK = "Send Back to Pending"

# Dedup lookup uses this field on Main v3 (existing behavior)
BILL_OVERVIEW_LINK_FIELD = "Bill Overview (Link)"

# Pending table stores overview link here (mirrors parse_bill_object output)
BILL_OVERVIEW_FIELD = "Bill Overview"
