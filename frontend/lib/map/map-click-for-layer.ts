import { NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import type { PublicStatesResponse } from "@/lib/api/types";
import type { MapLayerSelection } from "@/lib/map/bill-layers";

/** Which drawer `/states/{code}` to open after a map click for the active filter. */
export function drawerStateForMapClick(
  mapStateCode: string,
  mode: MapLayerSelection,
  statesResponse: PublicStatesResponse | undefined,
): string {
  if (mode === "nationalLegislation") {
    return NATIONAL_STATE_CODE;
  }

  if (mode === "dojInitiative") {
    const perState = statesResponse?.mapLayers?.dojInitiative.states;
    const hasPerStateDoj =
      perState != null && Object.keys(perState).length > 0;
    if (!hasPerStateDoj) {
      return NATIONAL_STATE_CODE;
    }
    return mapStateCode;
  }

  return mapStateCode;
}
