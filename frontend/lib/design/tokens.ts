/**
 * Programmatic tokens (SVG attributes, typed maps). CSS/Tailwind source of truth:
 * `tokens.css` — update both when values change.
 *
 * Map category fills: `mapFillForCategory()` in `lib/map/map-category-fill.ts`.
 */

/**
 * Hex from `frontend/public/ui/legend-*.svg`.
 */
export const policyStatusColor = {
  passed: "#3fbfa7",
  passedAdditional: "#7bedd8",
  /** legend-pending.svg circle */
  pendingBase: "#7bedd8",
  /** legend-pending.svg diagonal strokes; `--color-status-pending` for UI badges */
  pendingStripe: "#f8cf4d",
  failedAdditional: "#fadd82",
  failed: "#f8cf4d",
} as const;

export const MAP_PENDING_PATTERN_ID = "uic-map-pending-pattern";

export const mapInteraction = {
  stroke: "#1a1a1a",
  strokeWidth: "0.5",
  /** Dim non-selected states when one state is selected (see `--opacity-inactive`). */
  inactiveOpacity: "0.4",
  /** No Live row in API — usa.svg idle (#212121); not a legend category. */
  unlistedFill: "#212121",
} as const;

/** @deprecated Prefer Tailwind utilities from tokens.css */
export const layout = {
  artboardMaxPx: 1512,
  navInsetPx: 76,
  contentInsetPx: 123,
  contentGutterRightPx: 76,
  contentMapMaxPx: 1133,
  titleMaxPx: 394,
  titleInsetPx: 47,
  introMaxPx: 607,
  heroColumnGapPx: 103,
  filterInsetFromContentPx: 57,
  legendWidthPx: 351,
} as const;
