import type { PublicBill } from "@/lib/api/types";

/** Airtable Categories — keep in sync with backend `constants.ALLOWED_CATEGORIES`. */
export const DRAWER_TOPIC_FILTERS = [
  { key: "Taskforce", label: "Taskforce" },
  { key: "Day of Recognition", label: "Day of Recognition" },
  { key: "US Law Enforcement", label: "US Law Enforcement" },
  { key: "Tribal Law Enforcement", label: "Tribal Law Enforcement" },
  { key: "Data Collection", label: "Data Collection" },
  { key: "MMIP Relatives", label: "MMIP Relatives" },
] as const;

export type DrawerTopicFilterKey = (typeof DRAWER_TOPIC_FILTERS)[number]["key"];

/** OR match on `bill.categories`; empty selection = no topic constraint. */
export function billMatchesTopicFilters(
  bill: PublicBill,
  keys: readonly string[],
): boolean {
  if (keys.length === 0) return true;
  const billCats = new Set(
    (bill.categories ?? []).map((c) => String(c).trim().toLowerCase()),
  );
  return keys.some((key) => billCats.has(key.trim().toLowerCase()));
}
