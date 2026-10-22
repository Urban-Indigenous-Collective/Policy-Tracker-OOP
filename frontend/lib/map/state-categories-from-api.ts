import type { LegendCategory } from "@/lib/api/types";
import type { PublicStatesResponse } from "@/lib/api/types";

export function stateCategoriesFromResponse(
  data: PublicStatesResponse | undefined,
): Record<string, LegendCategory> {
  if (!data?.states) return {};
  const out: Record<string, LegendCategory> = {};
  for (const [code, entry] of Object.entries(data.states)) {
    out[code] = entry.category;
  }
  return out;
}
