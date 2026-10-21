import { MapLegend } from "@/components/map/MapLegend";
import { UsaMap } from "@/components/map/UsaMap";
import { CONTENT_MAP_MAX_PX } from "@/lib/layout/figma-layout";

type MapAndLegendProps = {
  onStateSelect?: (stateCode: string) => void;
};

/**
 * Map and legend as sibling columns on wide viewports only. Below xl, stack so
 * the map keeps full content width (side-by-side at ~1024px leaves ~450px for
 * the SVG — too small for taps and NE state detail).
 */
export function MapAndLegend({ onStateSelect }: MapAndLegendProps) {
  return (
    <div className="flex flex-col gap-8 sm:gap-10 xl:flex-row xl:items-end xl:gap-8">
      <div
        className="min-w-0 w-full xl:max-w-[1133px] xl:flex-1"
        style={{ maxWidth: CONTENT_MAP_MAX_PX }}
      >
        <UsaMap onStateSelect={onStateSelect} />
      </div>
      <div className="w-full shrink-0 xl:w-[351px] xl:pb-1">
        <MapLegend className="max-w-none xl:max-w-[351px]" />
      </div>
    </div>
  );
}
