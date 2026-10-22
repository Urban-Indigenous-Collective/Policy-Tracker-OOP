import type { PublicBill } from "@/lib/api/types";

export function filterDrawerBills(
  bills: PublicBill[],
  query: string,
): PublicBill[] {
  const q = query.trim().toLowerCase();
  if (!q) return bills;

  return bills.filter((bill) => {
    const haystack = [
      bill.billNumber,
      bill.name,
      bill.summary,
      bill.status,
      bill.progression,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}
