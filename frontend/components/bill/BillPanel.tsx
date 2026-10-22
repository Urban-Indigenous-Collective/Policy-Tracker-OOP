"use client";

import { useEffect, useRef, type TransitionEvent } from "react";

import { BillAnalysisView } from "@/components/bill/BillAnalysisView";
import { DrawerTopBorder } from "@/components/state/DrawerTopBorder";
import { useStatePrefetch } from "@/components/map/state-prefetch-context";
import { findBillBySlug } from "@/lib/api/bill-utils";
import { useBillDetail, useStateBills } from "@/lib/api/hooks";
import { drawerSlideStyle } from "@/lib/state/drawer-motion";

type BillPanelProps = {
  stateCode: string;
  slug: string;
  slideIn: boolean;
  onClose: () => void;
  onSlideTransitionEnd: (event: TransitionEvent<HTMLElement>) => void;
};

export function BillPanel({
  stateCode,
  slug,
  slideIn,
  onClose,
  onSlideTransitionEnd,
}: BillPanelProps) {
  const panelRef = useRef<HTMLElement>(null);
  const { prefetch, billDetail } = useStatePrefetch();
  const listQuery = useStateBills(stateCode, {
    initialData: prefetch?.state === stateCode ? prefetch.bills : null,
  });
  const fromList = findBillBySlug(listQuery.data?.bills ?? [], slug);
  const prefetched =
    billDetail && billDetail.state === stateCode && billDetail.slug === slug
      ? billDetail.detail
      : null;
  const recordId = prefetched?.bill.id ?? fromList?.id ?? null;
  const detailQuery = useBillDetail(recordId, { initialData: prefetched });
  const detailBill =
    detailQuery.data?.bill.slug === slug ? detailQuery.data.bill : null;
  const prefetchedAnalysis =
    prefetched?.bill && "uicPros" in prefetched.bill ? prefetched.bill : null;
  const bill = detailBill ?? prefetchedAnalysis ?? fromList ?? null;
  const listSettled = Boolean(listQuery.data) || listQuery.isError;
  const waitingForDetail =
    Boolean(recordId) &&
    detailQuery.isLoading &&
    !detailBill &&
    !prefetchedAnalysis;
  const showMissing =
    !bill && listSettled && !listQuery.isLoading && !waitingForDetail;

  useEffect(() => {
    panelRef.current?.focus({ preventScroll: true });
  }, [slug]);

  return (
    <aside
      ref={panelRef}
      data-mmip-state-panel
      data-mmip-bill-panel
      tabIndex={-1}
      role="dialog"
      aria-modal="false"
      aria-label="Bill details"
      onPointerDown={(event) => event.stopPropagation()}
      onTransitionEnd={onSlideTransitionEnd}
      style={drawerSlideStyle(slideIn)}
      className={`uic-bill-panel flex flex-col overflow-hidden border-l border-surface-border bg-background outline-none transition-transform motion-reduce:transition-none ${
        slideIn ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <DrawerTopBorder />
      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain pt-drawer-header-pt pl-page-x sm:pl-page-x-md lg:pl-bill-inset">
        <div className="sticky top-drawer-header-pt z-10 ml-auto w-fit pr-bill-dismiss-end">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close bill"
            className="inline-flex size-drawer-dismiss shrink-0 cursor-pointer items-center justify-center bg-background outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-accent"
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
        </div>

        {bill ? (
          <BillAnalysisView bill={bill} />
        ) : showMissing ? (
          <p className="uic-bill-title mt-bill-number-mt" role="alert">
            {detailQuery.isError || listQuery.isError
              ? "Could not load this policy."
              : "This policy is not available."}
          </p>
        ) : (
          <p className="uic-bill-title mt-bill-number-mt" aria-live="polite">
            Loading policy…
          </p>
        )}
      </div>
    </aside>
  );
}
