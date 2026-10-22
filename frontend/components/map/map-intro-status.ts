import { formatPolicyAsOfDate } from "@/lib/format/policy-as-of";
import type { PublicStatesResponse } from "@/lib/api/types";

export const EMPTY_POLICY_STATUS_LINE =
  "No live policies are published yet. Map colors will appear when bills are marked Live in Airtable.";

export function mapIntroStatusLine(
  resolved: PublicStatesResponse | undefined,
  loading: boolean,
): string | null {
  if (loading && !resolved) {
    return null;
  }

  const liveCount = resolved?.liveCount ?? 0;
  const hasMapStates = Object.keys(resolved?.states ?? {}).length > 0;
  const hasPublicPolicies = liveCount > 0 || hasMapStates;

  if (resolved && !hasPublicPolicies) {
    return EMPTY_POLICY_STATUS_LINE;
  }

  const asOf = resolved?.policyDataAsOf;
  if (asOf) {
    return `Policies current as of ${formatPolicyAsOfDate(asOf)}`;
  }

  if (resolved?.generatedAt) {
    return `Policies current as of ${formatPolicyAsOfDate(resolved.generatedAt)}`;
  }

  return null;
}
