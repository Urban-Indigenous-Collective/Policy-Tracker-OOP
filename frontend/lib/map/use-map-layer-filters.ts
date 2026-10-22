"use client";

import { useCallback, useState } from "react";

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

/** One active policy layer at a time; click active again to turn all off. */
export function useMapLayerFilters() {
  const [mode, setMode] = useState<MapLayerSelection>(DEFAULT_MAP_LAYER_MODE);

  const toggle = useCallback((key: MapLayerFilterKey) => {
    setMode((prev) => (prev === key ? null : key));
  }, []);

  const isActive = useCallback(
    (key: MapLayerFilterKey) => mode === key,
    [mode],
  );

  return { mode, toggle, isActive };
}
