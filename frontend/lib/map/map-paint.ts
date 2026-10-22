import { mapInteraction } from "@/lib/design/tokens";
import { LEGEND_FILL, type LegendCategory } from "@/lib/map/legend";
import { STATE_NAMES } from "@/lib/map/state-codes";

export const MAP_PAINT_STYLE_ID = "usa-map-paint-rules";

/** AK/HI are `<path id="US-XX">`; other states use `<g><use/></g>`. */
const PATH_ONLY_MAP_STATES = new Set(["AK", "HI"]);

const MAP_STATE_CODES = Object.keys(STATE_NAMES).sort();

/** API_V1: only states absent from `GET /api/v1/states` use neutral gray. */
export function fillForMapState(
  code: string,
  stateCategories: Record<string, LegendCategory>,
): string {
  const category = stateCategories[code];
  if (category && category in LEGEND_FILL) {
    return LEGEND_FILL[category];
  }
  return mapInteraction.unlistedFill;
}

export function buildMapPaintCss(
  stateCategories: Record<string, LegendCategory>,
  selectedState: string | null,
): string {
  const lines: string[] = [];

  for (const code of MAP_STATE_CODES) {
    const fill = fillForMapState(code, stateCategories);
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
        `#${id} > use { fill: ${fill} !important; opacity: ${opacity}; }`,
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
