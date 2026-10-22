import type { PublicBill } from "@/lib/api/types";

/** Main v3 single-select questions shown in the state drawer filter. */
export const DRAWER_EVAL_FILTERS = [
  {
    key: "mechanismsForEvaluation",
    label: "Mechanisms for evaluation",
    airtable: "Mechanisms for Evaluation?",
  },
  {
    key: "genderInclusiveLanguage",
    label: "Gender inclusive language",
    airtable: "Gender Inclusive Language?",
  },
  {
    key: "preventionEfforts",
    label: "Prevention efforts",
    airtable: "Prevention Efforts?",
  },
  {
    key: "survivorRelativeInput",
    label: "Survivor / relative input",
    airtable: "Level of Survivor / Relative Input?",
  },
  {
    key: "centeringIndigenousVoices",
    label: "Centering Indigenous voices",
    airtable: "Centering of Indigenous Voices?",
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
