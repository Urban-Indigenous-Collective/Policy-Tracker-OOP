export type LegendCategory =
  | "passed"
  | "passedAdditional"
  | "pending"
  | "failedAdditional"
  | "failed";

export const LEGEND_ITEMS: {
  id: LegendCategory;
  label: string;
  iconSrc: string;
}[] = [
  {
    id: "passed",
    label: "Passed",
    iconSrc: "/ui/legend-passed.svg",
  },
  {
    id: "passedAdditional",
    label: "Passed with additional legislation pending",
    iconSrc: "/ui/legend-passed-additional.svg",
  },
  {
    id: "pending",
    label: "Pending",
    iconSrc: "/ui/legend-pending.svg",
  },
  {
    id: "failedAdditional",
    label: "Failed with additional legislation pending",
    iconSrc: "/ui/legend-failed-additional.svg",
  },
  {
    id: "failed",
    label: "Failed",
    iconSrc: "/ui/legend-failed.svg",
  },
];

/** Placeholder map fills until Phase 2 API drives colors. */
export const LEGEND_FILL: Record<LegendCategory, string> = {
  passed: "#3fbfa7",
  passedAdditional: "#5ecdb9",
  pending: "#e8c547",
  failedAdditional: "#c9a832",
  failed: "#8a8a8a",
};
