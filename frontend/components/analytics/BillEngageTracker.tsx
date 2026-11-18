"use client";

import { useEffect } from "react";

import { trackBillEngage } from "@/lib/analytics/events";

type BillEngageTrackerProps = {
  stateCode: string;
  billSlug: string;
  /** Scroll container for intersection (bill panel). Defaults to viewport. */
  scrollRootRef?: React.RefObject<HTMLElement | null>;
};

/**
 * On unmount or bill change, reports dwell time and whether the analysis
 * grid (Pros/Cons/summary) entered the viewport while open.
 */
export function BillEngageTracker({
  stateCode,
  billSlug,
  scrollRootRef,
}: BillEngageTrackerProps) {
  useEffect(() => {
    const openedAt = Date.now();
    let scrolledAnalysis = false;
    let observer: IntersectionObserver | null = null;

    const attach = () => {
      const target = document.querySelector<HTMLElement>(
        "[data-bill-analysis-anchor], .uic-bill-detail-grid",
      );
      if (!target || observer) return;
      observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting)) {
            scrolledAnalysis = true;
          }
        },
        { root: scrollRootRef?.current ?? null, threshold: 0.15 },
      );
      observer.observe(target);
    };

    attach();
    const retry = window.setTimeout(attach, 300);

    return () => {
      window.clearTimeout(retry);
      observer?.disconnect();
      const dwellMs = Date.now() - openedAt;
      if (dwellMs < 500) return;
      trackBillEngage({
        stateCode,
        billSlug,
        dwellMs,
        scrolledAnalysis,
      });
    };
  }, [stateCode, billSlug, scrollRootRef]);

  return null;
}
