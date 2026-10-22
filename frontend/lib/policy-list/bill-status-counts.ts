import type { PublicBill } from "@/lib/api/types";
import { billStatusVariant } from "@/lib/bill/status-variant";

export type PolicyListStatusCounts = {
  passed: number;
  pending: number;
  rejected: number;
};

export function countPolicyListStatuses(bills: PublicBill[]): PolicyListStatusCounts {
  const counts: PolicyListStatusCounts = { passed: 0, pending: 0, rejected: 0 };
  for (const bill of bills) {
    const variant = billStatusVariant(bill);
    if (variant === "passed") counts.passed += 1;
    else if (variant === "pending") counts.pending += 1;
    else if (variant === "failed") counts.rejected += 1;
  }
  return counts;
}
