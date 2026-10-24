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

/** Drawer filter pill / option when open or selected — matches state title color. */
export function stateCategoryFilterActiveClass(
  category: LegendCategory | undefined,
): string {
  switch (category) {
    case "passed":
      return "border-status-passed text-status-passed";
    case "passedAdditional":
      return "border-status-passed-additional text-status-passed-additional";
    case "pending":
      return "border-status-pending text-status-pending";
    case "failedAdditional":
      return "border-status-failed-additional text-status-failed-additional";
    case "failed":
      return "border-status-failed text-status-failed";
    default:
      return "border-accent text-accent";
  }
}

export function stateCategoryFilterFocusRingClass(
  category: LegendCategory | undefined,
): string {
  switch (category) {
    case "passed":
      return "focus-visible:ring-status-passed";
    case "passedAdditional":
      return "focus-visible:ring-status-passed-additional";
    case "pending":
      return "focus-visible:ring-status-pending";
    case "failedAdditional":
      return "focus-visible:ring-status-failed-additional";
    case "failed":
      return "focus-visible:ring-status-failed";
    default:
      return "focus-visible:ring-accent";
  }
}
