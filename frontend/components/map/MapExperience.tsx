"use client";

import { useMemo } from "react";

import { MapAndLegend } from "@/components/map/MapAndLegend";
import { MapIntro } from "@/components/map/MapIntro";
import { mapIntroStatusLine } from "@/components/map/map-intro-status";
import { MapSummaryStats } from "@/components/map/MapSummaryStats";
import {
  StatePrefetchProvider,
  useStatePrefetch,
} from "@/components/map/state-prefetch-context";
import { StatePanelDrawer } from "@/components/state/StatePanelDrawer";
import { FilterChip } from "@/components/ui/FilterChip";
import { usePublicStates } from "@/lib/api/hooks";
import type { PublicStatesResponse } from "@/lib/api/types";
import { stateCategoriesFromResponse } from "@/lib/map/state-categories-from-api";
import { useCloseDrawerOutsideMap } from "@/lib/map/use-close-drawer-outside-map";
import { useMapSelection } from "@/lib/map/use-map-selection";

const FILTER_LABELS = [
  "NATIONAL LEGISLATION",
  "STATE LEGISLATION",
  "DOJ INITIATIVE",
  "EXECUTIVE ORDERS",
] as const;

type MapExperienceProps = {
  initialStates?: PublicStatesResponse | null;
  children?: React.ReactNode;
};

function MapExperienceInner({
  initialStates = null,
  children = null,
}: MapExperienceProps) {
  const { selectedState, onMapStateClick, closeState } = useMapSelection();
  const { prefetch } = useStatePrefetch();
  const { data, isLoading, isError, error } = usePublicStates({
    initialData: initialStates,
  });
  const resolvedStates = data ?? initialStates ?? undefined;
  const statsLoading = isLoading && !resolvedStates;

  const stateCategories = useMemo(
    () => stateCategoriesFromResponse(resolvedStates),
    [resolvedStates],
  );

  const introStatusLine = mapIntroStatusLine(resolvedStates, statsLoading);

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
          selectedState={selectedState}
          onStateSelect={onMapStateClick}
        />
      </section>

      <section
        className="mt-filter-section-top min-w-0 w-full overflow-x-clip border-t border-surface-border pt-filter-section-pt"
        aria-label="Policy type filters"
      >
        <div
          className="mx-auto flex w-fit max-w-full min-w-0 flex-wrap items-center justify-center gap-x-section gap-y-5 xl:mx-0 xl:w-full xl:flex-nowrap xl:justify-start xl:gap-x-nav-gap xl:gap-y-0 xl:pl-filter-inset"
          role="group"
        >
          {FILTER_LABELS.map((label) => (
            <FilterChip key={label} label={label} />
          ))}
        </div>
      </section>

      <StatePanelDrawer
        stateCode={selectedState}
        stateCategories={stateCategories}
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
