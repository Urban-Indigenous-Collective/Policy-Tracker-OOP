"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";

import { StatePrefetchProvider, useStatePrefetch } from "@/components/map/state-prefetch-context";
import { fetchBillById } from "@/lib/api/client";
import { publicApiKeys } from "@/lib/api/query-keys";
import { PolicyListBillDrawer } from "@/components/policy-list/PolicyListBillDrawer";
import { PolicyListStateSection } from "@/components/policy-list/PolicyListStateSection";
import { PolicyListToolbar } from "@/components/policy-list/PolicyListToolbar";
import type { PublicBill, PublicStatesResponse } from "@/lib/api/types";
import { filterDrawerBills } from "@/lib/state/filter-drawer-bills";
import type { DrawerFilterKey } from "@/lib/state/drawer-eval-filters";
import { policyListStateCategory } from "@/lib/policy-list/state-category";
import { sortPolicyListStateCodes } from "@/lib/policy-list/sort-state-codes";

type PolicyListViewProps = {
  billsByState: Record<string, PublicBill[]>;
  statesResponse?: PublicStatesResponse | null;
};

type BillSelection = {
  stateCode: string;
  slug: string;
  billId: string;
  bill: PublicBill;
};

function PolicyListViewInner({
  billsByState,
  statesResponse = null,
}: PolicyListViewProps) {
  const { setPrefetch } = useStatePrefetch();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [evalFilters, setEvalFilters] = useState<DrawerFilterKey[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [billSelection, setBillSelection] = useState<BillSelection | null>(null);

  const filteredByState = useMemo(() => {
    const next: Record<string, PublicBill[]> = {};
    for (const [code, bills] of Object.entries(billsByState)) {
      const filtered = filterDrawerBills(bills, searchQuery, evalFilters);
      if (filtered.length > 0) {
        next[code] = filtered;
      }
    }
    return next;
  }, [billsByState, evalFilters, searchQuery]);

  const stateCodes = useMemo(
    () => sortPolicyListStateCodes(Object.keys(filteredByState)),
    [filteredByState],
  );

  const filtersActive =
    evalFilters.length > 0 || searchQuery.trim().length > 0;

  const openBill = useCallback(
    (stateCode: string, bill: PublicBill) => {
      const bills = billsByState[stateCode];
      if (bills?.length) {
        setPrefetch({
          state: stateCode,
          bills: {
            state: stateCode,
            bills,
            generatedAt: new Date().toISOString(),
            cacheAgeSeconds: 0,
          },
        });
      }
      void queryClient.prefetchQuery({
        queryKey: publicApiKeys.bill(bill.id),
        queryFn: () => fetchBillById(bill.id),
      });
      setBillSelection({
        stateCode,
        slug: bill.slug,
        billId: bill.id,
        bill,
      });
    },
    [billsByState, queryClient, setPrefetch],
  );

  const closeBill = useCallback(() => {
    setBillSelection(null);
  }, []);

  useEffect(() => {
    if (!billSelection) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [billSelection]);

  useEffect(() => {
    if (!billSelection) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeBill();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [billSelection, closeBill]);

  return (
    <>
    <div className="mx-auto w-full max-w-policy-list pt-policy-list-top">
      <div className="flex flex-col">
        <PolicyListToolbar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          searchOpen={searchOpen}
          onSearchOpenChange={setSearchOpen}
          evalFilters={evalFilters}
          onEvalFiltersChange={setEvalFilters}
          filtersOpen={filtersOpen}
          onFiltersOpenChange={setFiltersOpen}
        />

        {stateCodes.length === 0 ? (
          <p className="uic-policy-list-toolbar-to-content font-sans text-drawer-bill-body text-muted">
            {filtersActive
              ? "No policies match your search or filters."
              : "No live policies are published yet."}
          </p>
        ) : (
          <div className="uic-policy-list-toolbar-to-content flex flex-col">
            {stateCodes.map((code) => (
              <PolicyListStateSection
                key={code}
                stateCode={code}
                bills={filteredByState[code] ?? []}
                stateCategory={policyListStateCategory(
                  code,
                  statesResponse,
                  filteredByState[code] ?? [],
                )}
                onBillSelect={openBill}
              />
            ))}
          </div>
        )}
      </div>
    </div>
    <PolicyListBillDrawer
      stateCode={billSelection?.stateCode ?? null}
      billSlug={billSelection?.slug ?? null}
      billId={billSelection?.billId ?? null}
      fallbackBill={billSelection?.bill ?? null}
      onClose={closeBill}
    />
    </>
  );
}

export function PolicyListView(props: PolicyListViewProps) {
  return (
    <StatePrefetchProvider>
      <PolicyListViewInner {...props} />
    </StatePrefetchProvider>
  );
}
