"use client";

import { useCallback, useMemo } from "react";

import { MapSelectionAnalytics } from "@/components/analytics/MapSelectionAnalytics";
import { EmbedDashboardCta } from "@/components/embed/EmbedDashboardCta";
import { MapAndLegend } from "@/components/map/MapAndLegend";
import { MapIntro } from "@/components/map/MapIntro";
import { mapIntroStatusLine } from "@/components/map/map-intro-status";
import { MapSummaryStats } from "@/components/map/MapSummaryStats";
import { MapBillNavProvider } from "@/components/map/map-bill-nav-context";
import {
  StatePrefetchProvider,
  useStatePrefetch,
} from "@/components/map/state-prefetch-context";
import { StatePanelDrawer } from "@/components/state/StatePanelDrawer";
import { FilterToggle } from "@/components/ui/FilterToggle";
import { usePublicStates, useStateBills } from "@/lib/api/hooks";
import type { PublicStatesResponse } from "@/lib/api/types";
import { isSvgMapStateCode, NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import { trackMapLayerToggle } from "@/lib/analytics/events";
import { setNextSelectionSource } from "@/lib/analytics/selection-source";
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
  /**
   * `embed` = iframe slice (stats + map + filters; no intro hero).
   * Selection stays in-memory so the iframe does not navigate to `/states/...`.
   */
  variant?: "default" | "embed";
};

function MapExperienceInner({
  initialStates = null,
  children = null,
  variant = "default",
}: MapExperienceProps) {
  const {
    selectedState,
    selectedBillSlug,
    onMapStateClick,
    closeState,
    closeBill,
    selectState,
    selectBill,
  } = useMapSelection(variant === "embed" ? "local" : "url");
  const showIntro = variant === "default";
  const embed = variant === "embed";
  const selectionSource = embed ? "embed" : "map";
  const openBillInEmbed = useCallback(
    (slug: string) => {
      setNextSelectionSource("embed");
      selectBill(slug);
    },
    [selectBill],
  );
  const mapHighlightedState =
    selectedState && isSvgMapStateCode(selectedState) ? selectedState : null;
  const { prefetch } = useStatePrefetch();
  const { data, isLoading, isError, error } = usePublicStates({
    initialData: initialStates,
  });
  const resolvedStates = data ?? initialStates ?? undefined;
  const statsLoading = isLoading && !resolvedStates;

  const { mode: mapLayerMode, toggle: toggleMapLayer, isActive } =
    useMapLayerFilters(selectedState);

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
    [nationalBillsForLayers],
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
      setNextSelectionSource(selectionSource);
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
      selectionSource,
    ],
  );

  useCloseDrawerOutsideMap(selectedState, closeState);

  const initialBills =
    selectedState && prefetch?.state === selectedState
      ? prefetch.bills
      : null;

  return (
    <MapBillNavProvider selectBill={embed ? openBillInEmbed : null}>
      <MapSelectionAnalytics
        selectedState={selectedState}
        selectedBillSlug={selectedBillSlug}
      />
      <div className={embed ? "pb-2" : "pb-map-content-pb"}>
        {children}
        {showIntro ? (
          <MapIntro
            statusLine={introStatusLine}
            statusBusy={statsLoading && !introStatusLine}
          />
        ) : null}
        {embed ? (
          <div className="mt-2 flex flex-wrap items-center justify-center gap-x-12 gap-y-3 sm:mt-3 sm:gap-x-16">
            <MapSummaryStats
              summary={resolvedStates?.summary}
              loading={statsLoading}
              align="start"
            />
            <EmbedDashboardCta />
          </div>
        ) : (
          <MapSummaryStats
            summary={resolvedStates?.summary}
            loading={statsLoading}
            align="intro"
          />
        )}

        {isError ? (
          <p className="mt-section text-sm text-red-400" role="alert">
            {error instanceof Error
              ? error.message
              : "Could not load policy map data."}
          </p>
        ) : null}

        <section
          className={embed ? "mt-4" : "mt-section lg:mt-section-lg"}
          aria-label="Policy map"
        >
          <MapAndLegend
            stateCategories={stateCategories}
            selectedState={mapHighlightedState}
            onStateSelect={handleMapStateSelect}
          />
        </section>

        <section
          className={
            embed
              ? "mt-4 min-w-0 w-full overflow-x-clip border-t border-surface-border pt-4"
              : "mt-filter-section-top min-w-0 w-full overflow-x-clip border-t border-surface-border pt-filter-section-pt"
          }
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
                onToggle={() => {
                  const nextActive = !isActive(key);
                  trackMapLayerToggle({ layer: key, active: nextActive });
                  toggleMapLayer(key);
                }}
              />
            ))}
          </div>
        </section>

        <StatePanelDrawer
          stateCode={selectedState}
          billSlug={selectedBillSlug}
          statesResponse={resolvedStates}
          mapLayerMode={mapLayerMode}
          mapPaintFallback={mapPaintFallback}
          onClose={closeState}
          onCloseBill={closeBill}
          initialBills={initialBills}
        />
      </div>
    </MapBillNavProvider>
  );
}

export function MapExperience(props: MapExperienceProps) {
  return (
    <StatePrefetchProvider>
      <MapExperienceInner {...props} />
    </StatePrefetchProvider>
  );
}
