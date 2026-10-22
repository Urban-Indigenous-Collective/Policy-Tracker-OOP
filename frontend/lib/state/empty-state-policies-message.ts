import { STATE_NAMES } from "@/lib/map/state-codes";

/** Drawer copy when a map state has no Live MMIP bills in the API snapshot. */
export function emptyStatePoliciesMessage(stateCode: string): string {
  const name = STATE_NAMES[stateCode] ?? stateCode;
  return `No MMIP policies have been passed in ${name} since 2020.`;
}
