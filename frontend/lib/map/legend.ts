import { policyStatusColor } from "@/lib/design/tokens";

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

/** Map fills until Phase 2 API drives colors per state. */
export const LEGEND_FILL: Record<LegendCategory, string> = {
  passed: policyStatusColor.passed,
  passedAdditional: policyStatusColor.passedAdditional,
  pending: policyStatusColor.pending,
  failedAdditional: policyStatusColor.failedAdditional,
  failed: policyStatusColor.failed,
};
