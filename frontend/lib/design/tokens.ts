/**
 * Programmatic tokens (SVG attributes, typed maps). CSS/Tailwind source of truth:
 * `tokens.css` — update both when values change.
 */
import type { LegendCategory } from "@/lib/map/legend";

export const policyStatusColor = {
  passed: "#3fbfa7",
  passedAdditional: "#5ecdb9",
  pending: "#e8c547",
  failedAdditional: "#c9a832",
  failed: "#8a8a8a",
} as const satisfies Record<LegendCategory, `#${string}`>;

export const mapInteraction = {
  stroke: "#1a1a1a",
  strokeWidth: "0.5",
  selectedOpacity: "0.42",
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
