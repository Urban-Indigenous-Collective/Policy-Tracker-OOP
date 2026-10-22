"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

import { DrawerTopBorder } from "@/components/state/DrawerTopBorder";
import { StateDrawerSearch } from "@/components/state/StateDrawerSearch";
import { StateBillList } from "@/components/state/StateBillList";
import { emptyStatePoliciesMessage } from "@/lib/state/empty-state-policies-message";
import { filterDrawerBills } from "@/lib/state/filter-drawer-bills";
import { useStateBills } from "@/lib/api/hooks";
import type { PublicStateBillsResponse } from "@/lib/api/types";
import type { LegendCategory } from "@/lib/map/legend";
import { stateCategoryTitleClass } from "@/lib/map/state-category-title-class";
import { STATE_NAMES } from "@/lib/map/state-codes";

type StatePanelProps = {
  stateCode: string;
  stateCategory?: LegendCategory;
  onClose: () => void;
  initialBills?: PublicStateBillsResponse | null;
  slideIn?: boolean;
  slideInDurationMs?: number;
  slideOutDurationMs?: number;
  onSlideTransitionEnd?: (event: React.TransitionEvent<HTMLElement>) => void;
};

/** In: accelerates, slight overshoot at rest. Out: ease-in — lingers then exits fast. */
const SLIDE_IN_EASE = "cubic-bezier(0.38, 0, 0.52, 1.38)";
const SLIDE_OUT_EASE = "cubic-bezier(0.72, 0, 0.98, 0.35)";

export function StatePanel({
  stateCode,
  stateCategory,
  onClose,
  initialBills = null,
  slideIn = true,
  slideInDurationMs = 440,
  slideOutDurationMs = 340,
  onSlideTransitionEnd,
}: StatePanelProps) {
  const titleId = useId();
  const searchId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const { data, isLoading, isError, error } = useStateBills(stateCode, {
    initialData: initialBills,
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    panelRef.current?.focus();
  }, [stateCode]);

  useEffect(() => {
    setSearchQuery("");
  }, [stateCode]);

  const name = (STATE_NAMES[stateCode] ?? stateCode).toUpperCase();
  const allBills = data?.bills ?? [];
  const filteredBills = useMemo(
    () => filterDrawerBills(allBills, searchQuery),
    [allBills, searchQuery],
  );
  const policyCount = allBills.length;
  const hasPolicies = policyCount > 0;
  const titleColorClass = hasPolicies
    ? stateCategoryTitleClass(stateCategory)
    : "text-foreground";

  return (
    <aside
      ref={panelRef}
      data-mmip-state-panel
      onPointerDown={(event) => event.stopPropagation()}
      tabIndex={-1}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      onTransitionEnd={onSlideTransitionEnd}
      style={{
        transitionDuration: slideIn
          ? `${slideInDurationMs}ms`
          : `${slideOutDurationMs}ms`,
        transitionTimingFunction: slideIn ? SLIDE_IN_EASE : SLIDE_OUT_EASE,
      }}
      className={`fixed inset-y-0 right-0 z-[110] flex w-full max-w-[100vw] flex-col border-l border-surface-border bg-background outline-none transition-transform motion-reduce:transition-none sm:max-w-none sm:w-state-drawer ${
        slideIn ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <DrawerTopBorder />
        <div className="relative px-drawer-x pt-drawer-header-pt pb-8">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="absolute top-drawer-header-pt right-drawer-x flex size-drawer-dismiss cursor-pointer items-center justify-center outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-accent"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/ui/dismiss.svg"
              alt=""
              width={28}
              height={28}
              className="size-drawer-dismiss"
              aria-hidden
            />
          </button>

          <h2
            id={titleId}
            className={`uic-drawer-state-title text-drawer-state-title font-mono font-bold leading-drawer-state-title mt-drawer-title-mt pr-10 ${titleColorClass}`}
          >
            {name}
          </h2>

          <div className="relative mt-drawer-meta-mt min-h-drawer-filter-pill">
            <p className="uic-drawer-policies-count" aria-live="polite">
              {isLoading && !data ? "…" : policyCount} POLICIES
            </p>
            {hasPolicies ? (
              <span
                className="absolute top-0 left-drawer-filter-from-content inline-flex h-drawer-filter-pill w-drawer-filter-pill items-center justify-center rounded-drawer-filter border border-foreground font-sans text-drawer-filter font-semibold tracking-drawer-filter text-foreground uppercase"
                aria-hidden
              >
                Filter
              </span>
            ) : null}
          </div>

          {hasPolicies ? (
            <StateDrawerSearch
              id={searchId}
              value={searchQuery}
              onChange={setSearchQuery}
            />
          ) : null}

          <div className={hasPolicies ? "mt-drawer-list-mt" : "mt-drawer-search-mt"}>
            {isLoading && !data ? (
              <p className="uic-drawer-bill-body-regular text-muted" aria-live="polite">
                Loading policies…
              </p>
            ) : null}
            {isError ? (
              <p className="uic-drawer-bill-body-regular text-red-400" role="alert">
                {error instanceof Error ? error.message : "Could not load bills."}
              </p>
            ) : null}
            {data && !hasPolicies ? (
              <p className="uic-drawer-bill-body-regular text-foreground" aria-live="polite">
                {emptyStatePoliciesMessage(stateCode)}
              </p>
            ) : null}
            {data && hasPolicies ? (
              <StateBillList
                stateCode={stateCode}
                bills={filteredBills}
                emptyMessage={
                  searchQuery.trim()
                    ? "No policies match your search."
                    : undefined
                }
              />
            ) : null}
          </div>
        </div>
      </div>
    </aside>
  );
}
