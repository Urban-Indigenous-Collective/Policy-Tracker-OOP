import type { PublicBill } from "@/lib/api/types";
import type { StatusBadgeProps } from "@/components/ui/StatusBadge";

/** Badge color — Main v3 ``Status`` wins; progression is fallback when status is empty. */
export function billStatusVariant(
  bill: PublicBill,
): NonNullable<StatusBadgeProps["variant"]> {
  const status = bill.status.trim().toLowerCase();
  if (status === "passed") return "passed";
  if (status === "failed") return "failed";
  if (status === "pending") return "pending";

  const text = `${bill.status} ${bill.progression}`.toLowerCase();
  if (text.includes("pass") || text.includes("enacted") || text.includes("signed")) {
    return "passed";
  }
  if (text.includes("fail") || text.includes("veto") || text.includes("dead")) {
    return "failed";
  }
  if (text.includes("pending") || text.includes("committee") || text.includes("introduced")) {
    return "pending";
  }
  return "neutral";
}
