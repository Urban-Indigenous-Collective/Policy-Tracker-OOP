"use client";

import { MapAndLegend } from "@/components/map/MapAndLegend";
import { MapIntro } from "@/components/map/MapIntro";
import { MapSummaryStats } from "@/components/map/MapSummaryStats";
import { FilterChip } from "@/components/ui/FilterChip";

const FILTER_LABELS = [
  "NATIONAL LEGISLATION",
  "STATE LEGISLATION",
  "DOJ INITIATIVE",
  "EXECUTIVE ORDERS",
] as const;

export default function Home() {
  return (
    <div className="pb-section-sm">
      <MapIntro />
      <MapSummaryStats />

      <section className="mt-section lg:mt-section-lg" aria-label="Policy map">
        <MapAndLegend
          onStateSelect={(code) => {
            if (process.env.NODE_ENV === "development") {
              console.info("[UsaMap] state selected:", code);
            }
          }}
        />
      </section>

      <section
        className="mt-filter-section-top min-w-0 w-full overflow-x-clip border-t border-surface-border pt-filter-section-pt pl-0 lg:pl-filter-inset"
        aria-label="Policy type filters"
      >
        {/*
          Filter row is width-driven (not a fixed “height”).
          Figma: four chips in one row on the 1512px artboard — use nowrap from xl (~1280+).
          Below xl: flex-wrap + centered group; chips wrap only when the row runs out of width.
        */}
        <div className="flex w-full justify-center xl:justify-start">
          <div
            className="flex w-fit max-w-full min-w-0 flex-wrap items-center justify-center gap-x-section gap-y-5 xl:w-full xl:flex-nowrap xl:justify-start xl:gap-x-nav-gap xl:gap-y-0"
            role="group"
          >
            {FILTER_LABELS.map((label) => (
              <FilterChip key={label} label={label} />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
