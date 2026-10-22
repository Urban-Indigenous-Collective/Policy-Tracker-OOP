import { NATIONAL_STATE_CODE, isSvgMapStateCode } from "@/lib/api/state-code";
import type { PublicBill } from "@/lib/api/types";
import { isDojInitiativeBill } from "@/lib/map/doj-detection";

export type MapLayerMode =
  | "stateLegislation"
  | "nationalLegislation"
  | "dojInitiative";

/** `null` = all filters off (map neutral). */
export type MapLayerSelection = MapLayerMode | null;

export const DEFAULT_MAP_LAYER_MODE: MapLayerMode = "stateLegislation";

export function isStateLegislationBill(bill: PublicBill): boolean {
  if (!isSvgMapStateCode(bill.state)) return false;
  if (isDojInitiativeBill(bill)) return false;
  return true;
}

export function isNationalLegislationBill(bill: PublicBill): boolean {
  if (bill.state !== NATIONAL_STATE_CODE) return false;
  if (isDojInitiativeBill(bill)) return false;
  return true;
}

export { isDojInitiativeBill } from "@/lib/map/doj-detection";

export function billMatchesMapLayer(
  bill: PublicBill,
  mode: MapLayerSelection,
): boolean {
  if (!mode) return false;
  if (mode === "stateLegislation") return isStateLegislationBill(bill);
  if (mode === "nationalLegislation") return isNationalLegislationBill(bill);
  return isDojInitiativeBill(bill);
}

/** Drawer list for the active map filter (same rules as map layers). */
export function filterBillsForMapLayer(
  bills: PublicBill[],
  mode: MapLayerSelection,
): PublicBill[] {
  if (!mode) return [];
  return bills.filter((bill) => billMatchesMapLayer(bill, mode));
}
