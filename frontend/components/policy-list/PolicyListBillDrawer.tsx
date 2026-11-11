"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { BillPanelDrawer } from "@/components/bill/BillPanelDrawer";
import type { PublicBill } from "@/lib/api/types";

type PolicyListBillDrawerProps = {
  stateCode: string | null;
  billSlug: string | null;
  billId: string | null;
  fallbackBill?: PublicBill | null;
  onClose: () => void;
};

export function PolicyListBillDrawer({
  stateCode,
  billSlug,
  billId,
  fallbackBill = null,
  onClose,
}: PolicyListBillDrawerProps) {
  const [portalReady, setPortalReady] = useState(false);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  if (!portalReady || !stateCode || !billSlug) return null;

  return createPortal(
    <BillPanelDrawer
      stateCode={stateCode}
      billSlug={billSlug}
      recordId={billId}
      fallbackBill={fallbackBill}
      onClose={onClose}
      fullscreen
    />,
    document.body,
  );
}
