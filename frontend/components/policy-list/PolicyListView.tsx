"use client";

import { useMemo, useState } from "react";

import { PolicyListStateSection } from "@/components/policy-list/PolicyListStateSection";
import { PolicyListToolbar } from "@/components/policy-list/PolicyListToolbar";
import type { PublicBill, PublicStatesResponse } from "@/lib/api/types";
import { filterDrawerBills } from "@/lib/state/filter-drawer-bills";
import type { DrawerEvalFilterKey } from "@/lib/state/drawer-eval-filters";
import { policyListStateCategory } from "@/lib/policy-list/state-category";
import { sortPolicyListStateCodes } from "@/lib/policy-list/sort-state-codes";

type PolicyListViewProps = {
  billsByState: Record<string, PublicBill[]>;
  statesResponse?: PublicStatesResponse | null;
};

export function PolicyListView({
  billsByState,
  statesResponse = null,
}: PolicyListViewProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [evalFilters, setEvalFilters] = useState<DrawerEvalFilterKey[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);

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

  return (
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
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
