# Airtable Pending Table Schema

The **Pending** table mirrors the live **Main v3** analysis columns plus review workflow fields.
Create this table manually in the same Airtable base before running discovery.

## Mirrored bill fields (from `bill_processor.parse_bill_object`)

| Field | Type |
|-------|------|
| State | Single line text |
| Title | Single line text (Airtable may use `Name` on Main v3 — Pending uses `Title`) |
| Bill Number | Single line text |
| Status | Single line text |
| Progression | Single line text |
| Chamber | Single line text |
| Chamber Details | Long text |
| Bill Overview | URL |
| Bill Text | URL |
| Optional Link | URL |
| Summary | Long text |
| UIC Pros | Long text |
| UIC Cons | Long text |
| Mechanisms for Evaluation? | Single select: Yes, No, Somewhat |
| Mechanisms for Evaluation | Long text |
| Gender Inclusive Language? | Single select: Yes, No, Somewhat |
| Gender Inclusive Explanation | Long text |
| Prevention Efforts? | Single select: Yes, No |
| Prevention Efforts | Long text |
| Level of Survivor / Relative Input? | Single select: Yes, No, Somewhat |
| Level of Survivor / Relative Input | Long text |
| Centering of Indigenous Voices? | Single select: Yes, No, Somewhat |
| Centering of Indigenous Voices | Long text |
| Sponsors | Long text |
| Indigenous Sponsorship | Long text |
| Session | Single line text |
| Categories | Single line text |
| Last Update | Date |
| Validation Warnings | Long text |

## Pending-only fields

| Field | Type | Values |
|-------|------|--------|
| Review Status | Single select | `Pending Review`, `Approved`, `Rejected` |
| Source | Single select | `LegiScan`, `State Site` |
| Relevance Confidence | Number (0–1) | LLM gate confidence |
| Relevance Rationale | Long text | Why the item was flagged as MMIP |
| Discovered On | Date | When the pipeline found it |

## Main v3 addition

Add to **Main v3**:

| Field | Type | Values |
|-------|------|--------|
| Review Status | Single select | `Live`, `Send Back to Pending` |

## Review workflow

1. Nightly discovery writes new records to **Pending** with `Review Status = Pending Review`.
2. Reviewer sets `Review Status = Approved` → approval sync copies to **Main v3** and deletes from Pending.
3. Reviewer sets `Review Status = Rejected` → approval sync deletes from Pending and marks rejected in local SQLite.
4. On **Main v3**, set `Review Status = Send Back to Pending` → approval sync moves record back to Pending.
