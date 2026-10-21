import type { CSSProperties } from "react";
import { MAP_SUMMARY_STATS } from "@/lib/mock/map-stats";
import {
  HERO_COLUMN_GAP_PX,
  TITLE_MAX_PX,
} from "@/lib/layout/figma-layout";

/** Figma: stats row at y≈552, aligned with intro column (x≈666). */
export function MapSummaryStats() {
  return (
    <div
      className="mt-6 grid gap-6 sm:mt-8 lg:grid-cols-[var(--title-col)_minmax(0,1fr)] lg:mt-10 lg:gap-[var(--hero-col-gap)]"
      style={
        {
          ["--title-col" as string]: `min(${TITLE_MAX_PX}px, 100%)`,
          ["--hero-col-gap" as string]: `${HERO_COLUMN_GAP_PX}px`,
        } as CSSProperties
      }
    >
      <div className="hidden lg:block" aria-hidden />
      <div className="flex flex-wrap gap-x-10 gap-y-2 font-mono text-base font-bold text-accent">
        <span>{MAP_SUMMARY_STATS.passed} PASSED</span>
        <span>{MAP_SUMMARY_STATS.pending} PENDING</span>
        <span>{MAP_SUMMARY_STATS.rejected} REJECTED</span>
      </div>
    </div>
  );
}
