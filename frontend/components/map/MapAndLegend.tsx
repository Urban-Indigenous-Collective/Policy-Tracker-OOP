import { MapLegend } from "@/components/map/MapLegend";
import { UsaMap } from "@/components/map/UsaMap";
import type { LegendCategory } from "@/lib/map/legend";

type MapAndLegendProps = {
  stateCategories: Record<string, LegendCategory>;
  selectedState?: string | null;
  onStateSelect?: (stateCode: string) => void;
};

/**
 * Map and legend as sibling columns on wide viewports only. Below xl, stack so
 * the map keeps full content width (side-by-side at ~1024px leaves ~450px for
 * the SVG — too small for taps and NE state detail).
 */
export function MapAndLegend({
  stateCategories,
  selectedState,
  onStateSelect,
}: MapAndLegendProps) {
  return (
    <div className="flex flex-col gap-section lg:gap-hero-stack-sm xl:flex-row xl:items-end xl:gap-section">
      <div className="min-w-0 w-full max-w-map xl:flex-1">
        <UsaMap
          stateCategories={stateCategories}
          selectedState={selectedState}
          onStateSelect={onStateSelect}
        />
      </div>
      <div className="w-full shrink-0 xl:w-legend xl:pb-1">
        <MapLegend className="max-w-none xl:max-w-legend" />
      </div>
    </div>
  );
}
