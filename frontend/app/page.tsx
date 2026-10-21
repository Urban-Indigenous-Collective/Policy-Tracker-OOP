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
    <div className="pb-8">
      <MapIntro />
      <MapSummaryStats />

      <section className="mt-8 lg:mt-10" aria-label="Policy map">
        <MapAndLegend
          onStateSelect={(code) => {
            if (process.env.NODE_ENV === "development") {
              console.info("[UsaMap] state selected:", code);
            }
          }}
        />
      </section>

      <section
        className="mt-20 min-w-0 w-full overflow-x-clip border-t border-white/10 pt-12 pl-0 lg:pl-[57px]"
        aria-label="Policy type filters"
      >
        <div
          className="grid w-full min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,17.5rem),1fr))] items-center gap-x-6 gap-y-5 sm:gap-x-8 2xl:flex 2xl:flex-nowrap 2xl:gap-x-10 2xl:gap-y-0"
          role="group"
        >
          {FILTER_LABELS.map((label) => (
            <FilterChip key={label} label={label} />
          ))}
        </div>
      </section>
    </div>
  );
}
