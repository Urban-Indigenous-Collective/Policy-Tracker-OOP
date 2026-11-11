"use client";

import { useEffect, useRef, type TransitionEvent } from "react";

import { BillAnalysisView } from "@/components/bill/BillAnalysisView";
import { DrawerTopBorder } from "@/components/state/DrawerTopBorder";
import { useStatePrefetch } from "@/components/map/state-prefetch-context";
import { findBillBySlug } from "@/lib/api/bill-utils";
import { useBillDetail, useStateBills } from "@/lib/api/hooks";
import type { PublicBill } from "@/lib/api/types";
import { billStatusFocusRingClass } from "@/lib/bill/status-classes";
import { billStatusVariant } from "@/lib/bill/status-variant";
import { drawerSlideStyle } from "@/lib/state/drawer-motion";

type BillPanelProps = {
  stateCode: string;
  slug: string;
  slideIn: boolean;
  onClose: () => void;
  onSlideTransitionEnd: (event: TransitionEvent<HTMLElement>) => void;
  /** Policy list: full-viewport panel instead of map layout beside state drawer. */
  fullscreen?: boolean;
  /** When known (e.g. policy list row), skip waiting on the state bill list query. */
  recordId?: string | null;
  /** Policy list row bill — show immediately while detail refetches. */
  fallbackBill?: PublicBill | null;
};

function detailBillFromQuery(
  data: { bill: PublicBill } | undefined,
  slug: string,
  recordId: string | null,
): PublicBill | null {
  const bill = data?.bill;
  if (!bill) return null;
  const normalizedSlug = slug.trim();
  if (bill.slug === normalizedSlug) return bill;
  if (recordId && bill.id === recordId) return bill;
  return null;
}

export function BillPanel({
  stateCode,
  slug,
  slideIn,
  onClose,
  onSlideTransitionEnd,
  fullscreen = false,
  recordId: recordIdProp = null,
  fallbackBill = null,
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
  const recordId =
    recordIdProp ?? prefetched?.bill.id ?? fromList?.id ?? null;
  const detailQuery = useBillDetail(recordId, { initialData: prefetched });
  const detailBill = detailBillFromQuery(detailQuery.data, slug, recordId);
  const prefetchedAnalysis =
    prefetched?.bill && "uicPros" in prefetched.bill ? prefetched.bill : null;
  const listBill =
    fromList ??
    (fallbackBill &&
    (fallbackBill.slug === slug.trim() ||
      (recordId && fallbackBill.id === recordId))
      ? fallbackBill
      : null);
  const waitingForDetail =
    Boolean(recordId) &&
    !detailBill &&
    !prefetchedAnalysis &&
    !listBill &&
    !detailQuery.isError &&
    detailQuery.isPending;
  const bill = detailBill ?? prefetchedAnalysis ?? listBill ?? null;
  const listSettled =
    Boolean(recordIdProp) || Boolean(listQuery.data) || listQuery.isError;
  const showMissing =
    !bill && listSettled && !listQuery.isLoading && !waitingForDetail;
  const dismissFocusRingClass = bill
    ? billStatusFocusRingClass[billStatusVariant(bill)]
    : "focus-visible:ring-accent";

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
      aria-modal={fullscreen ? "true" : "false"}
      aria-label="Bill details"
      onPointerDown={(event) => event.stopPropagation()}
      onTransitionEnd={onSlideTransitionEnd}
      style={drawerSlideStyle(slideIn)}
      className={`uic-bill-panel flex flex-col overflow-hidden border-l border-surface-border bg-background outline-none transition-transform motion-reduce:transition-none ${
        fullscreen ? "uic-bill-panel--fullscreen" : ""
      } ${slideIn ? "translate-x-0" : "translate-x-full"}`}
    >
      <DrawerTopBorder />
      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain pt-drawer-header-pt pl-page-x sm:pl-page-x-md lg:pl-bill-inset">
        <div className="sticky top-drawer-header-pt z-10 ml-auto w-fit pr-bill-dismiss-end">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close bill"
            className={`inline-flex size-drawer-dismiss shrink-0 cursor-pointer items-center justify-center bg-background outline-none hover:opacity-80 focus-visible:ring-2 ${dismissFocusRingClass}`}
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
          <BillAnalysisView key={slug} bill={bill} />
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
