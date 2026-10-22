import { mapInteraction } from "@/lib/design/tokens";
import { mapFillForState } from "@/lib/map/map-category-fill";
import { STATE_NAMES } from "@/lib/map/state-codes";
import type { LegendCategory } from "@/lib/map/legend";

export const MAP_PAINT_STYLE_ID = "usa-map-paint-rules";

/** AK/HI are `<path id="US-XX">`; other states use `<g><use/></g>`. */
const PATH_ONLY_MAP_STATES = new Set(["AK", "HI"]);

const MAP_STATE_CODES = Object.keys(STATE_NAMES).sort();

function buildMapOutlineCss(): string {
  const stroke = mapInteraction.stroke;
  const width = mapInteraction.strokeWidth;
  return `
svg g[id^="US-"] > path {
  display: none !important;
}
svg g[id^="US-"] > use {
  stroke: ${stroke} !important;
  stroke-width: ${width}px !important;
  stroke-linejoin: round;
}
path#US-AK,
path#US-HI {
  stroke: ${stroke} !important;
  stroke-width: ${width}px !important;
}
`.trim();
}

export function buildMapPaintCss(
  stateCategories: Record<string, LegendCategory>,
  selectedState: string | null,
): string {
  const lines: string[] = [buildMapOutlineCss()];

  for (const code of MAP_STATE_CODES) {
    const fill = mapFillForState(code, stateCategories);
    const opacity =
      selectedState && code !== selectedState
        ? mapInteraction.inactiveOpacity
        : "1";
    const id = `US-${code}`;

    if (PATH_ONLY_MAP_STATES.has(code)) {
      lines.push(
        `path#${id} { fill: ${fill} !important; opacity: ${opacity}; }`,
      );
    } else {
      lines.push(
        `#${id} { opacity: ${opacity}; }`,
        `#${id} > use { fill: ${fill} !important; }`,
      );
    }
  }

  return lines.join("\n");
}

export function applyMapPaintStyles(
  container: HTMLElement,
  stateCategories: Record<string, LegendCategory>,
  selectedState: string | null,
): void {
  let styleEl = container.querySelector<HTMLStyleElement>(
    `#${MAP_PAINT_STYLE_ID}`,
  );
  if (!styleEl) {
    styleEl = document.createElement("style");
    styleEl.id = MAP_PAINT_STYLE_ID;
    container.prepend(styleEl);
  }
  styleEl.textContent = buildMapPaintCss(stateCategories, selectedState);
}
