import { NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import { STATE_NAMES } from "@/lib/map/state-codes";

/** Drawer copy when a jurisdiction has no Live MMIP bills in the API snapshot. */
export function emptyStatePoliciesMessage(stateCode: string): string {
  if (stateCode === NATIONAL_STATE_CODE) {
    return "No MMIP policies have been passed at the federal level since 2020.";
  }
  const name = STATE_NAMES[stateCode] ?? stateCode;
  return `No MMIP policies have been passed in ${name} since 2020.`;
}
