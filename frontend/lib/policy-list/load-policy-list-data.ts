import { fetchPublicStates, fetchStateBills } from "@/lib/api/client";
import type { PublicBill, PublicStatesResponse } from "@/lib/api/types";
import { NATIONAL_STATE_CODE } from "@/lib/api/state-code";

export type PolicyListData = {
  states: PublicStatesResponse;
  billsByState: Record<string, PublicBill[]>;
};

function stateCodesWithPolicies(states: PublicStatesResponse): string[] {
  const fromMap = Object.entries(states.states)
    .filter(([, entry]) => entry.billCount > 0)
    .map(([code]) => code);

  const codes = new Set(fromMap);
  if (!codes.has(NATIONAL_STATE_CODE)) {
    codes.add(NATIONAL_STATE_CODE);
  }

  return [...codes];
}

export async function loadPolicyListData(): Promise<PolicyListData> {
  const states = await fetchPublicStates({ base: "server" });
  const codes = stateCodesWithPolicies(states);

  const pairs = await Promise.all(
    codes.map(async (code) => {
      try {
        const response = await fetchStateBills(code, { base: "server" });
        return [code, response.bills] as const;
      } catch {
        return [code, [] as PublicBill[]] as const;
      }
    }),
  );

  const billsByState: Record<string, PublicBill[]> = {};
  for (const [code, bills] of pairs) {
    if (bills.length > 0) {
      billsByState[code] = bills;
    }
  }

  return { states, billsByState };
}
