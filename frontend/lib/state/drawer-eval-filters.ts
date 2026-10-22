import type { PublicBill } from "@/lib/api/types";

/** Main v3 single-select questions shown in the state drawer filter. */
export const DRAWER_EVAL_FILTERS = [
  {
    key: "mechanismsForEvaluation",
    label: "Mechanisms for evaluation",
    airtable: "Mechanisms for Evaluation?",
    justificationKey: "mechanismsForEvaluationJustification",
    justificationLabel: "Mechanisms for evaluation justification",
  },
  {
    key: "genderInclusiveLanguage",
    label: "Gender inclusive language",
    airtable: "Gender Inclusive Language?",
    justificationKey: "genderInclusiveLanguageJustification",
    justificationLabel: "Gender inclusive language justification",
  },
  {
    key: "preventionEfforts",
    label: "Prevention efforts",
    airtable: "Prevention Efforts?",
    justificationKey: "preventionEffortsJustification",
    justificationLabel: "Prevention efforts justification",
  },
  {
    key: "survivorRelativeInput",
    label: "Survivor / relative input",
    airtable: "Level of Survivor / Relative Input?",
    justificationKey: "survivorRelativeInputJustification",
    justificationLabel: "Survivor / relative input justification",
  },
  {
    key: "centeringIndigenousVoices",
    label: "Centering Indigenous voices",
    airtable: "Centering of Indigenous Voices?",
    justificationKey: "centeringIndigenousVoicesJustification",
    justificationLabel: "Centering Indigenous voices justification",
  },
] as const;

export type DrawerEvalFilterKey = (typeof DRAWER_EVAL_FILTERS)[number]["key"];

const AFFIRMATIVE_EVAL = new Set(["yes", "somewhat"]);

export function billMatchesEvalFilters(
  bill: PublicBill,
  keys: readonly DrawerEvalFilterKey[],
): boolean {
  if (keys.length === 0) return true;
  return keys.every((key) =>
    AFFIRMATIVE_EVAL.has((bill[key] ?? "").trim().toLowerCase()),
  );
}
