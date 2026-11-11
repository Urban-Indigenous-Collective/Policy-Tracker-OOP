"use client";

import { useMemo, useState } from "react";

import { PolicyListBillRow } from "@/components/policy-list/PolicyListBillRow";
import { StateSubscribeBell } from "@/components/state/StateSubscribeBell";
import { StateSubscribeModal } from "@/components/state/StateSubscribeModal";
import { isStateSubscribeEnabled } from "@/lib/api/subscriptions";
import type { PublicBill } from "@/lib/api/types";
import type { LegendCategory } from "@/lib/map/legend";
import { stateCategoryTitleClass } from "@/lib/map/state-category-title-class";
import { countPolicyListStatuses } from "@/lib/policy-list/bill-status-counts";
import { policyListStateDisplayName } from "@/lib/policy-list/sort-state-codes";

const INITIAL_VISIBLE = 3;

type PolicyListStateSectionProps = {
  stateCode: string;
  bills: PublicBill[];
  stateCategory?: LegendCategory;
  onBillSelect: (stateCode: string, bill: PublicBill) => void;
};

function ExpandChevron({ className }: { className?: string }) {
  return (
    <svg
      width={24}
      height={24}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={className}
    >
      <path
        d="M6 9l6 6 6-6"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function PolicyListStateSection({
  stateCode,
  bills,
  stateCategory,
  onBillSelect,
}: PolicyListStateSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const [subscribeOpen, setSubscribeOpen] = useState(false);
  const subscribeEnabled = isStateSubscribeEnabled();
  const counts = useMemo(() => countPolicyListStatuses(bills), [bills]);
  const hiddenCount = Math.max(0, bills.length - INITIAL_VISIBLE);
  const visibleBills = expanded || hiddenCount === 0 ? bills : bills.slice(0, INITIAL_VISIBLE);
  const displayName = policyListStateDisplayName(stateCode);
  const titleColorClass = stateCategoryTitleClass(stateCategory);

  const billList = (
    <ul className="flex flex-col gap-drawer-row">
      {visibleBills.map((bill) => (
        <PolicyListBillRow
          key={bill.id}
          stateCode={stateCode}
          bill={bill}
          onSelect={onBillSelect}
        />
      ))}
    </ul>
  );

  return (
    <section
      aria-labelledby={`policy-list-state-${stateCode}`}
      className="grid gap-policy-list-header-to-rows pb-policy-list-section-gap lg:grid-cols-[minmax(0,var(--grid-title-col))_minmax(0,1fr)] lg:gap-x-policy-list-col-gap lg:gap-y-0"
    >
      {subscribeEnabled ? (
        <>
          <h2
            id={`policy-list-state-${stateCode}`}
            className={`font-mono text-hero font-bold leading-hero lg:pt-1 ${titleColorClass}`}
          >
            {displayName}
          </h2>
          <div className="mb-3 flex items-center justify-end lg:mb-4 lg:min-h-[var(--text-hero)] lg:pt-1">
            <StateSubscribeBell
              label={`Subscribe to updates for ${displayName}`}
              onClick={() => setSubscribeOpen(true)}
            />
          </div>
          <p className="mt-0 flex flex-wrap gap-x-nav-gap gap-y-1 font-mono text-body font-bold text-foreground lg:mt-policy-list-state-stats">
            <span>{counts.passed} PASSED</span>
            <span>{counts.pending} PENDING</span>
            <span>{counts.rejected} REJECTED</span>
          </p>
          <div className="min-w-0 w-full">
            {billList}
            <StateSubscribeModal
              stateCode={stateCode}
              open={subscribeOpen}
              onClose={() => setSubscribeOpen(false)}
            />
          </div>
        </>
      ) : (
        <>
          <div className="min-w-0 lg:pt-1">
            <h2
              id={`policy-list-state-${stateCode}`}
              className={`font-mono text-hero font-bold leading-hero ${titleColorClass}`}
            >
              {displayName}
            </h2>
            <p className="mt-policy-list-state-stats flex flex-wrap gap-x-nav-gap gap-y-1 font-mono text-body font-bold text-foreground">
              <span>{counts.passed} PASSED</span>
              <span>{counts.pending} PENDING</span>
              <span>{counts.rejected} REJECTED</span>
            </p>
          </div>
          <div className="min-w-0 w-full">{billList}</div>
        </>
      )}

      {hiddenCount > 0 && !expanded ? (
        <div className="mt-policy-list-expand-mt flex w-full flex-col items-center gap-policy-list-expand-label-gap lg:col-span-2">
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="max-w-full px-2 outline-none transition-opacity hover:opacity-70 focus-visible:ring-2 focus-visible:ring-accent"
          >
            <span className="uic-policy-list-expand-label block max-w-full">
              View {hiddenCount} more {hiddenCount === 1 ? "policy" : "policies"}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setExpanded(true)}
            aria-label={`View ${hiddenCount} more policies for ${displayName}`}
            className="flex size-policy-list-expand items-center justify-center rounded-full border border-foreground/25 p-policy-list-expand-chevron-pad text-foreground outline-none transition-opacity hover:opacity-70 focus-visible:ring-2 focus-visible:ring-accent"
          >
            <ExpandChevron />
          </button>
        </div>
      ) : null}
    </section>
  );
}
