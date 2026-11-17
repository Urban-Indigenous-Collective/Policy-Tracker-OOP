import type { PublicBill } from "@/lib/api/types";

import {
  billMatchesEvalFilters,
  type DrawerFilterKey,
} from "@/lib/state/drawer-eval-filters";
import { billMatchesTopicFilters } from "@/lib/state/drawer-topic-filters";

export function filterDrawerBills(
  bills: PublicBill[],
  query: string,
  evalFilters: readonly DrawerFilterKey[] = [],
  topicFilters: readonly string[] = [],
): PublicBill[] {
  const matched = bills.filter(
    (bill) =>
      billMatchesTopicFilters(bill, topicFilters) &&
      billMatchesEvalFilters(bill, evalFilters),
  );
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
      ...(bill.categories ?? []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}
