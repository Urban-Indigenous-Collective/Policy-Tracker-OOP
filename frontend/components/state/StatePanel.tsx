"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { DrawerTopBorder } from "@/components/state/DrawerTopBorder";
import {
  StateDrawerFilterButton,
  StateDrawerFilterMenu,
} from "@/components/state/StateDrawerFilter";
import { StateDrawerSearch } from "@/components/state/StateDrawerSearch";
import { StateBillList } from "@/components/state/StateBillList";
import { StateSubscribeBell } from "@/components/state/StateSubscribeBell";
import { StateSubscribeModal } from "@/components/state/StateSubscribeModal";
import { emptyStatePoliciesMessage } from "@/lib/state/empty-state-policies-message";
import type { DrawerFilterKey } from "@/lib/state/drawer-eval-filters";
import { filterDrawerBills } from "@/lib/state/filter-drawer-bills";
import {
  filterBillsForMapLayer,
  type MapLayerSelection,
} from "@/lib/map/bill-layers";
import { useStateBills } from "@/lib/api/hooks";
import { isStateSubscribeEnabled } from "@/lib/api/subscriptions";
import type { PublicStateBillsResponse } from "@/lib/api/types";
import type { LegendCategory } from "@/lib/map/legend";
import { stateCategoryTitleClass } from "@/lib/map/state-category-title-class";
import { NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import { STATE_NAMES } from "@/lib/map/state-codes";
import { drawerSlideStyle } from "@/lib/state/drawer-motion";

type StatePanelProps = {
  stateCode: string;
  stateCategory?: LegendCategory;
  mapLayerMode: MapLayerSelection;
  onClose: () => void;
  onCloseBill?: () => void;
  billPanelOpen?: boolean;
  initialBills?: PublicStateBillsResponse | null;
  slideIn?: boolean;
  onSlideTransitionEnd?: (event: React.TransitionEvent<HTMLElement>) => void;
};

export function StatePanel({
  stateCode,
  stateCategory,
  onClose,
  onCloseBill,
  billPanelOpen = false,
  mapLayerMode,
  initialBills = null,
  slideIn = true,
  onSlideTransitionEnd,
}: StatePanelProps) {
  const titleId = useId();
  const searchId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const metaRowRef = useRef<HTMLDivElement>(null);
  const policiesCountRef = useRef<HTMLParagraphElement>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [evalFilters, setEvalFilters] = useState<DrawerFilterKey[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [subscribeOpen, setSubscribeOpen] = useState(false);
  /** Match Filter→bell gap to Policies→Filter gap. */
  const [metaControlGapPx, setMetaControlGapPx] = useState<number | null>(null);
  const filterTrayId = useId();
  const subscribeEnabled = isStateSubscribeEnabled();
  const { data, isLoading, isError, error } = useStateBills(stateCode, {
    initialData: initialBills,
  });
  const dismissBillLatch = useRef(false);
  const [prevResetKey, setPrevResetKey] = useState(
    () => `${stateCode}:${mapLayerMode}`,
  );
  const resetKey = `${stateCode}:${mapLayerMode}`;
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey);
    setSearchQuery("");
    setEvalFilters([]);
    setFiltersOpen(false);
    setSubscribeOpen(false);
  }

  useEffect(() => {
    if (!billPanelOpen) {
      dismissBillLatch.current = false;
    }
  }, [billPanelOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (subscribeOpen) {
        setSubscribeOpen(false);
        return;
      }
      if (filtersOpen) {
        setFiltersOpen(false);
        return;
      }
      if (billPanelOpen && !dismissBillLatch.current) {
        dismissBillLatch.current = true;
        onCloseBill?.();
        return;
      }
      onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [subscribeOpen, filtersOpen, billPanelOpen, onClose, onCloseBill]);

  useEffect(() => {
    if (billPanelOpen) return;
    panelRef.current?.focus({ preventScroll: true });
  }, [billPanelOpen, stateCode]);

  const name =
    stateCode === NATIONAL_STATE_CODE
      ? "NATIONAL"
      : (STATE_NAMES[stateCode] ?? stateCode).toUpperCase();
  const allBills = useMemo(
    () => filterBillsForMapLayer(data?.bills ?? [], mapLayerMode),
    [data?.bills, mapLayerMode],
  );
  const filteredBills = useMemo(
    () => filterDrawerBills(allBills, searchQuery, evalFilters),
    [allBills, searchQuery, evalFilters],
  );
  const policyCount = allBills.length;
  const hasPolicies = policyCount > 0;
  const filtersActive = evalFilters.length > 0 || searchQuery.trim().length > 0;
  const shownCount = filtersActive ? filteredBills.length : policyCount;
  const titleColorClass = hasPolicies
    ? stateCategoryTitleClass(stateCategory)
    : "text-foreground";

  const effectiveMetaControlGapPx =
    hasPolicies && subscribeEnabled ? metaControlGapPx : null;

  useLayoutEffect(() => {
    if (!hasPolicies || !subscribeEnabled) return;
    const row = metaRowRef.current;
    const policies = policiesCountRef.current;
    if (!row || !policies) return;

    const measure = () => {
      const raw = getComputedStyle(row)
        .getPropertyValue("--spacing-drawer-filter-from-content")
        .trim();
      const rootFontPx = parseFloat(
        getComputedStyle(document.documentElement).fontSize,
      );
      let filterLeftPx = row.getBoundingClientRect().left;
      if (raw.endsWith("rem")) {
        filterLeftPx += parseFloat(raw) * rootFontPx;
      } else if (raw.endsWith("px")) {
        filterLeftPx += parseFloat(raw);
      } else {
        filterLeftPx += 12.125 * rootFontPx;
      }
      const gap = filterLeftPx - policies.getBoundingClientRect().right;
      setMetaControlGapPx(Number.isFinite(gap) ? Math.max(0, gap) : null);
    };

    // Defer so the layout effect only subscribes; setState runs from the observer/rAF callback.
    const rafId = requestAnimationFrame(measure);
    const ro = new ResizeObserver(measure);
    ro.observe(row);
    ro.observe(policies);
    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
    };
  }, [hasPolicies, subscribeEnabled, shownCount, name]);

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
      style={drawerSlideStyle(slideIn)}
      className={`fixed inset-y-0 right-0 z-[110] flex w-full max-w-[100vw] flex-col overflow-x-visible border-l border-surface-border bg-background outline-none transition-transform motion-reduce:transition-none sm:max-w-none sm:w-state-drawer ${
        slideIn ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <div className="min-h-0 flex-1 overflow-x-visible overflow-y-auto overscroll-contain">
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

          <div className="flex w-full max-w-drawer-content flex-col">
          <h2
            id={titleId}
            className={`uic-drawer-state-title text-drawer-state-title font-mono font-bold leading-drawer-state-title mt-drawer-title-mt max-w-[calc(100%-2.75rem)] pr-10 ${titleColorClass}`}
          >
            {name}
          </h2>

          <div
            ref={metaRowRef}
            className="relative mt-drawer-meta-mt min-h-drawer-filter-pill"
          >
            <p
              ref={policiesCountRef}
              className="uic-drawer-policies-count w-max"
              aria-live="polite"
            >
              {isLoading && !data ? "…" : shownCount} POLICIES
            </p>
            {hasPolicies ? (
              <div
                className="absolute top-0 left-drawer-filter-from-content flex items-center"
                style={
                  subscribeEnabled && effectiveMetaControlGapPx != null
                    ? { gap: `${effectiveMetaControlGapPx}px` }
                    : undefined
                }
              >
                <StateDrawerFilterButton
                  open={filtersOpen}
                  active={evalFilters.length > 0}
                  controlsId={filterTrayId}
                  stateCategory={stateCategory}
                  placement="toolbar"
                  onToggle={() => setFiltersOpen((open) => !open)}
                />
                {subscribeEnabled ? (
                  <StateSubscribeBell
                    label={`Subscribe to updates for ${name}`}
                    onClick={() => setSubscribeOpen(true)}
                  />
                ) : null}
              </div>
            ) : subscribeEnabled ? (
              <div className="absolute top-0 right-0">
                <StateSubscribeBell
                  label={`Subscribe to updates for ${name}`}
                  onClick={() => setSubscribeOpen(true)}
                />
              </div>
            ) : null}
            {hasPolicies ? (
              <StateDrawerFilterMenu
                id={filterTrayId}
                open={filtersOpen}
                selected={evalFilters}
                stateCategory={stateCategory}
                onChange={setEvalFilters}
                onClose={() => setFiltersOpen(false)}
              />
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
                    : evalFilters.length
                      ? "No policies match the selected filters."
                      : undefined
                }
              />
            ) : null}
          </div>
          </div>
        </div>
      </div>
      {subscribeEnabled && subscribeOpen ? (
        <StateSubscribeModal
          key={stateCode}
          stateCode={stateCode}
          open
          onClose={() => setSubscribeOpen(false)}
        />
      ) : null}
    </aside>
  );
}
