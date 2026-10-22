import type { PublicBill } from "@/lib/api/types";

import {
  billMatchesEvalFilters,
  type DrawerEvalFilterKey,
} from "@/lib/state/drawer-eval-filters";

export function filterDrawerBills(
  bills: PublicBill[],
  query: string,
  evalFilters: readonly DrawerEvalFilterKey[] = [],
): PublicBill[] {
  const matched = bills.filter((bill) => billMatchesEvalFilters(bill, evalFilters));
  const q = query.trim().toLowerCase();
  if (!q) return matched;

  return matched.filter((bill) => {
    const haystack = [
      bill.billNumber,
      bill.name,
      bill.summary,
      bill.session,
      bill.status,
      bill.progression,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}
