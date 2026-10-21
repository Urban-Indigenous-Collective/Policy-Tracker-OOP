import { MAP_SUMMARY_STATS } from "@/lib/mock/map-stats";

/** Figma: stats row at y≈552, aligned with intro column (x≈666). */
export function MapSummaryStats() {
  return (
    <div className="mt-section-sm grid gap-section-sm sm:mt-section lg:grid-cols-[var(--grid-title-col)_minmax(0,1fr)] lg:mt-section-lg lg:gap-hero-col">
      <div className="hidden lg:block" aria-hidden />
      <div className="flex flex-wrap gap-x-nav-gap gap-y-2 font-mono text-body font-bold text-accent">
        <span>{MAP_SUMMARY_STATS.passed} PASSED</span>
        <span>{MAP_SUMMARY_STATS.pending} PENDING</span>
        <span>{MAP_SUMMARY_STATS.rejected} REJECTED</span>
      </div>
    </div>
  );
}
