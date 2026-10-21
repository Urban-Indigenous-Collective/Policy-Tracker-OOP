import Image from "next/image";
import { LEGEND_ITEMS } from "@/lib/map/legend";

type MapLegendProps = {
  className?: string;
};

/** Sits beside the map in the right gutter — never overlaid on state shapes. */
export function MapLegend({ className = "" }: MapLegendProps) {
  return (
    <aside
      className={`w-full shrink-0 ${className}`.trim()}
      aria-label="Map legend"
    >
      <ul className="space-y-3">
        {LEGEND_ITEMS.map((item) => (
          <li key={item.id} className="flex items-start gap-3">
            <Image
              src={item.iconSrc}
              alt=""
              width={25}
              height={25}
              className="mt-0.5 size-legend-icon shrink-0"
              aria-hidden
            />
            <span className="text-body-md font-bold leading-snug text-foreground">
              {item.label}
            </span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
