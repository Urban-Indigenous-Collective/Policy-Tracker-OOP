"use client";

import { useCallback, useEffect, useState } from "react";

import { NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import {
  DEFAULT_MAP_LAYER_MODE,
  type MapLayerMode,
  type MapLayerSelection,
} from "@/lib/map/bill-layers";

export type MapLayerFilterKey = MapLayerMode;

const FILTER_LABELS: Record<MapLayerFilterKey, string> = {
  stateLegislation: "STATE LEGISLATION",
  nationalLegislation: "NATIONAL LEGISLATION",
  dojInitiative: "DOJ INITIATIVE",
};

export const MAP_FILTER_ROWS: MapLayerFilterKey[] = [
  "nationalLegislation",
  "stateLegislation",
  "dojInitiative",
];

export function filterLabelForKey(key: MapLayerFilterKey): string {
  return FILTER_LABELS[key];
}

function layerForOpenDrawer(stateCode: string | null): MapLayerSelection | null {
  if (stateCode === NATIONAL_STATE_CODE) return "nationalLegislation";
  return null;
}

/** One active policy layer at a time; click active again to turn all off. */
export function useMapLayerFilters(selectedState: string | null) {
  const [mode, setMode] = useState<MapLayerSelection>(() =>
    layerForOpenDrawer(selectedState) ?? DEFAULT_MAP_LAYER_MODE,
  );

  useEffect(() => {
    const routeLayer = layerForOpenDrawer(selectedState);
    if (routeLayer) setMode(routeLayer);
  }, [selectedState]);

  const toggle = useCallback((key: MapLayerFilterKey) => {
    setMode((prev) => (prev === key ? null : key));
  }, []);

  const isActive = useCallback(
    (key: MapLayerFilterKey) => mode === key,
    [mode],
  );

  return { mode, toggle, isActive };
}
