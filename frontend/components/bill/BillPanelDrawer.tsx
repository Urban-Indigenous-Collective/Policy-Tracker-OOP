"use client";

import { useLayoutEffect, useState } from "react";

import { BillPanel } from "@/components/bill/BillPanel";
import type { PublicBill } from "@/lib/api/types";
import { useDrawerSlide } from "@/lib/state/drawer-motion";

type BillPanelDrawerProps = {
  stateCode: string;
  billSlug: string | null;
  onClose: () => void;
  fullscreen?: boolean;
  recordId?: string | null;
  fallbackBill?: PublicBill | null;
};

/** Slides the bill detail out of the open state drawer. Same motion as that drawer. */
export function BillPanelDrawer({
  stateCode,
  billSlug,
  onClose,
  fullscreen = false,
  recordId = null,
  fallbackBill = null,
}: BillPanelDrawerProps) {
  const { activeKey: activeSlug, slideIn, onSlideTransitionEnd } =
    useDrawerSlide(billSlug);
  const [billState, setBillState] = useState(stateCode);

  useLayoutEffect(() => {
    if (!billSlug) return;
    setBillState(stateCode);
  }, [billSlug, stateCode]);

  if (!activeSlug) return null;

  return (
    <BillPanel
      stateCode={billState}
      slug={activeSlug}
      slideIn={slideIn}
      onClose={onClose}
      onSlideTransitionEnd={onSlideTransitionEnd}
      fullscreen={fullscreen}
      recordId={recordId}
      fallbackBill={fallbackBill}
    />
  );
}
