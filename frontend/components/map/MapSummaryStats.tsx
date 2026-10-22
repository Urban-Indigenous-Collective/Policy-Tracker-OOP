import type { MapSummary } from "@/lib/api/types";

type MapSummaryStatsProps = {
  summary: MapSummary | null | undefined;
  loading?: boolean;
};

function formatStat(value: number | undefined, loading: boolean): string {
  if (loading && value === undefined) return "…";
  if (value === undefined) return "—";
  return String(value);
}

/** Figma: stats row at y≈552, aligned with intro column (x≈666). */
export function MapSummaryStats({ summary, loading }: MapSummaryStatsProps) {
  const passed = formatStat(summary?.passed, Boolean(loading));
  const pending = formatStat(summary?.pending, Boolean(loading));
  const rejected = formatStat(summary?.rejected, Boolean(loading));

  return (
    <div className="mt-section-sm grid gap-section-sm sm:mt-section lg:grid-cols-[var(--grid-title-col)_minmax(0,1fr)] lg:mt-section-lg lg:gap-hero-col">
      <div className="hidden lg:block" aria-hidden />
      <div
        className="flex flex-wrap gap-x-nav-gap gap-y-2 font-mono text-body font-bold text-accent"
        aria-busy={loading}
      >
        <span>{passed} PASSED</span>
        <span>{pending} PENDING</span>
        <span>{rejected} REJECTED</span>
      </div>
    </div>
  );
}
