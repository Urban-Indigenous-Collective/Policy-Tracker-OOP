import { NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import { STATE_NAMES } from "@/lib/map/state-codes";

export function sortPolicyListStateCodes(codes: string[]): string[] {
  return [...codes].sort((a, b) => {
    if (a === NATIONAL_STATE_CODE && b !== NATIONAL_STATE_CODE) return -1;
    if (b === NATIONAL_STATE_CODE && a !== NATIONAL_STATE_CODE) return 1;
    const nameA = STATE_NAMES[a] ?? a;
    const nameB = STATE_NAMES[b] ?? b;
    return nameA.localeCompare(nameB, "en", { sensitivity: "base" });
  });
}

export function policyListStateDisplayName(code: string): string {
  if (code === NATIONAL_STATE_CODE) return "National";
  return STATE_NAMES[code] ?? code;
}
