import type { Metadata } from "next";

import { PolicyListView } from "@/components/policy-list/PolicyListView";
import { loadPolicyListData } from "@/lib/policy-list/load-policy-list-data";

export const instant = false;

export const metadata: Metadata = {
  title: "Policy list",
  description:
    "Browse MMIP-related legislation by U.S. state — passed, pending, and rejected policies with UIC analysis filters.",
  alternates: { canonical: "/policy-list" },
};

export default async function PolicyListPage() {
  let billsByState: Record<string, import("@/lib/api/types").PublicBill[]> = {};
  let statesResponse: import("@/lib/api/types").PublicStatesResponse | null = null;

  try {
    const data = await loadPolicyListData({ base: "server" });
    billsByState = data.billsByState;
    statesResponse = data.states;
  } catch {
    // Empty state; dev banner surfaces API issues.
  }

  return (
    <PolicyListView billsByState={billsByState} statesResponse={statesResponse} />
  );
}
