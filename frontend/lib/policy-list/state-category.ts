import { NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import type { PublicBill, PublicStatesResponse } from "@/lib/api/types";
import type { LegendCategory } from "@/lib/map/legend";
import { stateLegendCategory } from "@/lib/map/state-legend-category";

/** Map / legend category for a policy-list state block (mirrors drawer title coloring). */
export function policyListStateCategory(
  stateCode: string,
  statesResponse: PublicStatesResponse | null | undefined,
  bills: PublicBill[],
): LegendCategory | undefined {
  if (stateCode === NATIONAL_STATE_CODE) {
    return (
      statesResponse?.mapLayers?.nationalLegislation?.category ??
      stateLegendCategory(bills) ??
      undefined
    );
  }

  return (
    statesResponse?.states[stateCode]?.category ??
    stateLegendCategory(bills) ??
    undefined
  );
}
