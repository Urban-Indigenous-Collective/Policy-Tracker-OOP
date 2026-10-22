"use client";

import { useCallback, useMemo } from "react";

import { MapAndLegend } from "@/components/map/MapAndLegend";
import { MapIntro } from "@/components/map/MapIntro";
import { mapIntroStatusLine } from "@/components/map/map-intro-status";
import { MapSummaryStats } from "@/components/map/MapSummaryStats";
import {
  StatePrefetchProvider,
  useStatePrefetch,
} from "@/components/map/state-prefetch-context";
import { StatePanelDrawer } from "@/components/state/StatePanelDrawer";
import { FilterToggle } from "@/components/ui/FilterToggle";
import { usePublicStates, useStateBills } from "@/lib/api/hooks";
import type { PublicStatesResponse } from "@/lib/api/types";
import { isSvgMapStateCode, NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import { useCloseDrawerOutsideMap } from "@/lib/map/use-close-drawer-outside-map";
import {
  filterLabelForKey,
  MAP_FILTER_ROWS,
  useMapLayerFilters,
} from "@/lib/map/use-map-layer-filters";
import {
  deriveFallbackBillsFromNationalResponse,
  resolveMapPaintCategories,
} from "@/lib/map/resolve-map-paint-categories";
import { drawerStateForMapClick } from "@/lib/map/map-click-for-layer";
import { useMapSelection } from "@/lib/map/use-map-selection";

type MapExperienceProps = {
  initialStates?: PublicStatesResponse | null;
  children?: React.ReactNode;
};

function MapExperienceInner({
  initialStates = null,
  children = null,
}: MapExperienceProps) {
  const { selectedState, onMapStateClick, closeState, selectState } =
    useMapSelection();
  const mapHighlightedState =
    selectedState && isSvgMapStateCode(selectedState) ? selectedState : null;
  const { prefetch } = useStatePrefetch();
  const { data, isLoading, isError, error } = usePublicStates({
    initialData: initialStates,
  });
  const resolvedStates = data ?? initialStates ?? undefined;
  const statsLoading = isLoading && !resolvedStates;

  const { mode: mapLayerMode, toggle: toggleMapLayer, isActive } =
    useMapLayerFilters();

  const needsNationalFallback =
    !resolvedStates?.mapLayers &&
    (mapLayerMode === "nationalLegislation" ||
      mapLayerMode === "dojInitiative");
  const { data: nationalBillsForLayers } = useStateBills(
    needsNationalFallback ? NATIONAL_STATE_CODE : null,
  );

  const mapPaintFallback = useMemo(
    () =>
      nationalBillsForLayers?.bills?.length
        ? deriveFallbackBillsFromNationalResponse(nationalBillsForLayers.bills)
        : undefined,
    [nationalBillsForLayers?.bills],
  );

  const stateCategories = useMemo(
    () =>
      resolveMapPaintCategories(
        resolvedStates,
        mapLayerMode,
        mapPaintFallback,
      ),
    [resolvedStates, mapLayerMode, mapPaintFallback],
  );

  const introStatusLine = mapIntroStatusLine(resolvedStates, statsLoading);

  const handleMapStateSelect = useCallback(
    (code: string | null) => {
      if (!code) {
        closeState();
        return;
      }
      if (!mapLayerMode || mapLayerMode === "stateLegislation") {
        onMapStateClick(code);
        return;
      }
      const drawerCode = drawerStateForMapClick(
        code,
        mapLayerMode,
        resolvedStates,
      );
      if (selectedState === drawerCode) {
        closeState();
      } else {
        selectState(drawerCode);
      }
    },
    [
      closeState,
      mapLayerMode,
      onMapStateClick,
      resolvedStates,
      selectState,
      selectedState,
    ],
  );

  useCloseDrawerOutsideMap(selectedState, closeState);

  const initialBills =
    selectedState && prefetch?.state === selectedState
      ? prefetch.bills
      : null;

  return (
    <div className="pb-section-sm">
      {children}
      <MapIntro
        statusLine={introStatusLine}
        statusBusy={statsLoading && !introStatusLine}
      />
      <MapSummaryStats
        summary={resolvedStates?.summary}
        loading={statsLoading}
      />

      {isError ? (
        <p className="mt-section text-sm text-red-400" role="alert">
          {error instanceof Error
            ? error.message
            : "Could not load policy map data."}
        </p>
      ) : null}

      <section className="mt-section lg:mt-section-lg" aria-label="Policy map">
        <MapAndLegend
          stateCategories={stateCategories}
          selectedState={mapHighlightedState}
          onStateSelect={handleMapStateSelect}
        />
      </section>

      <section
        className="mt-filter-section-top min-w-0 w-full overflow-x-clip border-t border-surface-border pt-filter-section-pt"
        aria-label="Policy type filters"
      >
        <div
          className="mx-auto flex w-full max-w-full min-w-0 flex-wrap items-center justify-center gap-x-section gap-y-5 xl:flex-nowrap xl:gap-x-nav-gap"
          role="group"
        >
          {MAP_FILTER_ROWS.map((key) => (
            <FilterToggle
              key={key}
              label={filterLabelForKey(key)}
              active={isActive(key)}
              onToggle={() => toggleMapLayer(key)}
            />
          ))}
        </div>
      </section>

      <StatePanelDrawer
        stateCode={selectedState}
        statesResponse={resolvedStates}
        mapLayerMode={mapLayerMode}
        mapPaintFallback={mapPaintFallback}
        onClose={closeState}
        initialBills={initialBills}
      />
    </div>
  );
}

export function MapExperience(props: MapExperienceProps) {
  return (
    <StatePrefetchProvider>
      <MapExperienceInner {...props} />
    </StatePrefetchProvider>
  );
}
