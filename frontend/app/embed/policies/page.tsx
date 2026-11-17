import type { Metadata } from "next";

import { PolicyListView } from "@/components/policy-list/PolicyListView";
import { loadPolicyListData } from "@/lib/policy-list/load-policy-list-data";

export const instant = false;

export const metadata: Metadata = {
  title: "MMIP policy list embed",
  description:
    "Embeddable MMIP policy list — browse Live legislation by state without site nav or footer.",
  robots: { index: false, follow: false },
};

export default async function EmbedPoliciesPage() {
  let billsByState: Record<string, import("@/lib/api/types").PublicBill[]> = {};
  let statesResponse: import("@/lib/api/types").PublicStatesResponse | null =
    null;

  try {
    const data = await loadPolicyListData({ base: "server" });
    billsByState = data.billsByState;
    statesResponse = data.states;
  } catch {
    // Empty state; host page can still show chrome/CTA.
  }

  return (
    <PolicyListView
      billsByState={billsByState}
      statesResponse={statesResponse}
      compactTop
    />
  );
}
