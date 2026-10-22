import type { LegendCategory } from "@/lib/map/legend";
import { isNationalLegislationBill, type MapLayerSelection } from "@/lib/map/bill-layers";
import { isDojInitiativeBill } from "@/lib/map/doj-detection";
import type { PublicBill, PublicMapLayers, PublicStatesResponse } from "@/lib/api/types";
import { STATE_NAMES } from "@/lib/map/state-codes";
import { stateLegendCategory } from "@/lib/map/state-legend-category";

export type MapPaintFallback = {
  nationalBills?: PublicBill[];
  dojBills?: PublicBill[];
};

function paintUniform(
  category: LegendCategory,
): Record<string, LegendCategory> {
  const out: Record<string, LegendCategory> = {};
  for (const code of Object.keys(STATE_NAMES)) {
    out[code] = category;
  }
  return out;
}

function paintFromStateEntries(
  states: Record<string, { category: LegendCategory }>,
): Record<string, LegendCategory> {
  const out: Record<string, LegendCategory> = {};
  for (const [code, entry] of Object.entries(states)) {
    out[code] = entry.category;
  }
  return out;
}

function dojLayerPaint(
  layers: PublicMapLayers,
  fallback?: MapPaintFallback,
): Record<string, LegendCategory> {
  const perState = layers.dojInitiative.states;
  if (Object.keys(perState).length > 0) {
    return paintFromStateEntries(perState);
  }
  const category =
    layers.dojInitiative.category ??
    (fallback?.dojBills?.length
      ? stateLegendCategory(fallback.dojBills)
      : null);
  // Only paint the whole map when DOJ data is federal-only (no per-state rows).
  return category ? paintUniform(category) : {};
}

function nationalLayerPaint(
  layers: PublicMapLayers | undefined,
  fallback?: MapPaintFallback,
): Record<string, LegendCategory> {
  const category =
    layers?.nationalLegislation.category ??
    (fallback?.nationalBills?.length
      ? stateLegendCategory(
          fallback.nationalBills.filter(isNationalLegislationBill),
        )
      : null);
  return category ? paintUniform(category) : {};
}

/** Paint rules for the active map filter mode (see API `mapLayers`). */
export function resolveMapPaintCategories(
  data: PublicStatesResponse | undefined,
  mode: MapLayerSelection,
  fallback?: MapPaintFallback,
): Record<string, LegendCategory> {
  if (!mode) return {};

  const layers = data?.mapLayers;

  if (mode === "stateLegislation") {
    if (layers?.stateLegislation.states) {
      return paintFromStateEntries(layers.stateLegislation.states);
    }
    if (data?.states) {
      return paintFromStateEntries(data.states);
    }
    return {};
  }

  if (mode === "nationalLegislation") {
    return nationalLayerPaint(layers, fallback);
  }

  if (mode === "dojInitiative") {
    if (layers) {
      return dojLayerPaint(layers, fallback);
    }
    if (fallback?.dojBills?.length) {
      const category = stateLegendCategory(fallback.dojBills);
      return category ? paintUniform(category) : {};
    }
    return {};
  }

  return {};
}

export function drawerCategoryForState(
  data: PublicStatesResponse | undefined,
  mode: MapLayerSelection,
  stateCode: string,
  fallback?: MapPaintFallback,
): LegendCategory | undefined {
  if (stateCode === "National") {
    if (mode === "nationalLegislation") {
      const layers = data?.mapLayers;
      return (
        layers?.nationalLegislation.category ??
        (fallback?.nationalBills?.length
          ? stateLegendCategory(
              fallback.nationalBills.filter(isNationalLegislationBill),
            ) ?? undefined
          : undefined)
      );
    }
    if (mode === "dojInitiative") {
      const layers = data?.mapLayers;
      return (
        layers?.dojInitiative.category ??
        (fallback?.dojBills?.length
          ? stateLegendCategory(fallback.dojBills) ?? undefined
          : undefined)
      );
    }
    return undefined;
  }
  const painted = resolveMapPaintCategories(data, mode, fallback);
  return painted[stateCode];
}

/** Bills used to compute paint when `mapLayers` is absent (dev / stale API). */
export function deriveFallbackBillsFromNationalResponse(
  bills: PublicBill[],
): MapPaintFallback {
  return {
    nationalBills: bills,
    dojBills: bills.filter(isDojInitiativeBill),
  };
}

export function deriveFallbackBillsFromAllStateResponses(
  responses: PublicBill[],
): MapPaintFallback {
  const dojBills = responses.filter(isDojInitiativeBill);
  const nationalBills = responses.filter(isNationalLegislationBill);
  return { nationalBills, dojBills };
}
