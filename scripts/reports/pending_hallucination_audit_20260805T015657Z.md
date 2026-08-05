# Pending hallucination critic dry-run (20260805T015657Z)

## Summary

- Selected: 50
- Audited OK: 50
- Fetch failed: 0
- Empty source: 0
- Critic failed: 0

## Cohort stats

- **high_risk**: n=40 grounded=33 (82%) with_issues=7 suspect_fields=7
- **control**: n=10 grounded=9 (90%) with_issues=1 suspect_fields=1

## Top issue severities

- CriticSeverity.UNGROUNDED: 9
- CriticSeverity.FABRICATED_QUOTE: 1
- CriticSeverity.CONTRADICTS_EVAL: 7
- CriticSeverity.OVERSTATED: 8
- CriticSeverity.WRONG_CATEGORY: 1

## Top flagged fields

- UIC Pros: 10
- Summary: 4
- UIC Cons: 4
- Mechanisms for Evaluation: 2
- Prevention Efforts: 2
- Centering of Indigenous Voices: 1
- Level of Survivor / Relative Input: 1
- Categories: 1
- Gender Inclusive Language: 1

## Flagged records (sample)

- `rec08uSXpcyA8vzIf` [high_risk] US 'Native Youth and Tribal Officer Protection Act' grounded=False issues=5 Summary:CriticSeverity.UNGROUNDED; UIC Pros:CriticSeverity.UNGROUNDED; UIC Pros:CriticSeverity.UNGROUNDED
  - The analysis contains significant unsupported claims regarding interagency coordination, specific training mandates, and reporting requirements. The provided excerpt ends abruptly in Section 3, Subsec
- `rec2Hz0kt7plMkeap` [high_risk] WI 'National Day of Awareness for Missing and Murdered Indigenou' grounded=False issues=1 UIC Cons:CriticSeverity.UNGROUNDED
  - The analysis is largely grounded in the text, but the 'UIC Cons' section contains a claim about the 'absence of Indigenous sponsors' which cannot be verified from the provided excerpt (a Governor's Pr
- `rec2WxVh5EdEjT5tq` [high_risk] MN 'Research data protection provision for data on individuals' grounded=False issues=3 UIC Pros:CriticSeverity.FABRICATED_QUOTE; Summary:CriticSeverity.UNGROUNDED; Summary:CriticSeverity.UNGROUNDED
  - The existing analysis contains significant hallucinations in the 'UIC Pros' and 'Summary' fields. The source excerpt provided is limited to data privacy classifications (Sections 1-4) and minor termin
- `rec2vItDI6xfxUEpQ` [high_risk] NY 'Establishes a task force on missing women and girls who are ' grounded=False issues=4 Mechanisms for Evaluation:CriticSeverity.CONTRADICTS_EVAL; Prevention Efforts:CriticSeverity.CONTRADICTS_EVAL; Centering of Indigenous Voices:CriticSeverity.OVERSTATED
  - The analysis contains significant contradictions between the evaluation fields (marked 'No') and the explanatory text/quotes (which cite relevant sections). Specifically, 'Mechanisms for Evaluation' i
- `rec4CoAVgtuwxK0Nd` [high_risk] CO 'Missing Murdered Indigenous Relative License Plate' grounded=False issues=2 UIC Pros:CriticSeverity.CONTRADICTS_EVAL; UIC Pros:CriticSeverity.OVERSTATED
  - The analysis contains a direct contradiction in the 'UIC Pros' field. The evaluator marked 'Gender Inclusive Language' as 'No', but then listed in 'UIC Pros' that the legislation 'uses gender-inclusiv
- `rec7itTIJW4JAIaul` [high_risk] AK 'Missing or Murdered Indigenous Persons' grounded=False issues=4 UIC Pros:CriticSeverity.OVERSTATED; UIC Cons:CriticSeverity.CONTRADICTS_EVAL; Categories:CriticSeverity.UNGROUNDED
  - The analysis contains several unsupported claims. The 'UIC Pros' section hallucinates that the committee 'Establishes' the ATPSAC, whereas the text describes an existing committee's meeting and member
- `recERYX2aa4aX6w2o` [high_risk] MN 'Minnesota missing and murdered Indigenous relatives special ' grounded=False issues=2 UIC Pros:CriticSeverity.CONTRADICTS_EVAL; UIC Cons:CriticSeverity.CONTRADICTS_EVAL
  - The analysis contains a direct contradiction in the 'UIC Pros' field. The evaluator marked 'Gender Inclusive Language' as 'No', but the first point in 'UIC Pros' explicitly claims the bill 'Uses gende
- `recm66S9pWldCo9jm` [control] CA 'Emergency notification: Feather Alert: endangered indigenous' grounded=False issues=5 Summary:CriticSeverity.OVERSTATED; Gender Inclusive Language:CriticSeverity.OVERSTATED; Mechanisms for Evaluation:CriticSeverity.WRONG_CATEGORY
  - The analysis contains significant factual errors regarding the definition of the alert and the criteria for activation. Specifically, the Summary and UIC Pros claim the bill defines alerts for 'two-sp
