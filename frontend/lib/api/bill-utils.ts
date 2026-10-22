import type { PublicBill } from "@/lib/api/types";

export function findBillBySlug(
  bills: PublicBill[],
  slug: string,
): PublicBill | undefined {
  const normalized = slug.trim();
  return bills.find((b) => b.slug === normalized);
}
