import type { LegendCategory } from "@/lib/map/legend";
import {
  MAP_PENDING_PATTERN_ID,
  mapInteraction,
  policyStatusColor,
} from "@/lib/design/tokens";

/** Solid fills from `public/ui/legend-*.svg` (pending uses stripe pattern on map). */
const SOLID_MAP_FILL: Record<LegendCategory, string> = {
  passed: policyStatusColor.passed,
  passedAdditional: policyStatusColor.passedAdditional,
  pending: policyStatusColor.pendingBase,
  failedAdditional: policyStatusColor.failedAdditional,
  failed: policyStatusColor.failed,
};

export function mapFillForCategory(category: LegendCategory): string {
  if (category === "pending") {
    return `url(#${MAP_PENDING_PATTERN_ID})`;
  }
  return SOLID_MAP_FILL[category];
}

export function mapFillForState(
  code: string,
  stateCategories: Record<string, LegendCategory>,
): string {
  const category = stateCategories[code];
  if (category && category in SOLID_MAP_FILL) {
    return mapFillForCategory(category);
  }
  return mapInteraction.unlistedFill;
}
