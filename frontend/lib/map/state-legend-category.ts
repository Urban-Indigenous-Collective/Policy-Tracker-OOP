import type { LegendCategory } from "@/lib/map/legend";
import type { PublicBill } from "@/lib/api/types";

function normStatus(raw: string | undefined): string {
  return (raw ?? "").trim().toLowerCase();
}

/** Mirrors public_api/map_aggregate.state_legend_category. */
export function stateLegendCategory(bills: PublicBill[]): LegendCategory | null {
  if (bills.length === 0) return null;

  const statuses = bills.map((b) => normStatus(b.status));
  const hasPassed = statuses.includes("passed");
  const hasPending = statuses.includes("pending");
  const hasFailed = statuses.includes("failed");

  if (hasPassed) {
    return hasPending ? "passedAdditional" : "passed";
  }
  if (hasPending) {
    const nonPending = statuses.filter((s) => s !== "pending");
    if (
      nonPending.length > 0 &&
      nonPending.every((s) => s === "failed") &&
      hasFailed
    ) {
      return "failedAdditional";
    }
    return "pending";
  }
  if (hasFailed) return "failed";
  return "pending";
}
