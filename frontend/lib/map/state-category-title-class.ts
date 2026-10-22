import type { LegendCategory } from "@/lib/map/legend";

/** Drawer state name color — matches map / legend category fills. */
export function stateCategoryTitleClass(
  category: LegendCategory | undefined,
): string {
  switch (category) {
    case "passed":
      return "text-status-passed";
    case "passedAdditional":
      return "text-status-passed-additional";
    case "pending":
      return "text-status-pending";
    case "failedAdditional":
      return "text-status-failed-additional";
    case "failed":
      return "text-status-failed";
    default:
      return "text-foreground";
  }
}
