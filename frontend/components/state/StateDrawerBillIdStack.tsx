"use client";

import { useLayoutEffect, useRef, useState } from "react";

import { StateDrawerStatusPill } from "@/components/state/StateDrawerStatusPill";
import type { PublicBill } from "@/lib/api/types";

type StateDrawerBillIdStackProps = {
  billId: string;
  bill: PublicBill;
};

type StackLayout = "default" | "wrapped";

const STACK_WIDTH_REM = 7.8125;

function cssVarRemToPx(name: string, fallbackRem: number): number {
  const root = document.documentElement;
  const styles = getComputedStyle(root);
  const rem = parseFloat(styles.fontSize);
  const raw = styles.getPropertyValue(name).trim();
  if (!raw) return fallbackRem * rem;
  if (raw.endsWith("rem")) return parseFloat(raw) * rem;
  if (raw.endsWith("px")) return parseFloat(raw);
  return fallbackRem * rem;
}

function initialLayout(billId: string): StackLayout {
  const chars = billId.replace(/\s/g, "").length;
  return chars > 14 ? "wrapped" : "default";
}

/**
 * Bill id + status pill share `--width-drawer-bill-id-stack` (id column) on every row.
 * Long ids and status labels wrap inside that width.
 */
export function StateDrawerBillIdStack({ billId, bill }: StateDrawerBillIdStackProps) {
  const measureRef = useRef<HTMLSpanElement>(null);
  const [layout, setLayout] = useState<StackLayout>(() => initialLayout(billId));

  useLayoutEffect(() => {
    const measure = measureRef.current;
    if (!measure) return;

    const intrinsic = measure.getBoundingClientRect().width;
    const colPx = cssVarRemToPx(
      "--width-drawer-bill-id-stack",
      STACK_WIDTH_REM,
    );

    setLayout(intrinsic > colPx + 0.5 ? "wrapped" : "default");
  }, [billId]);

  const idClass =
    layout === "wrapped"
      ? "uic-drawer-bill-id-constrained text-left"
      : "uic-drawer-bill-id-constrained uic-drawer-bill-id-centered";

  return (
    <div className="relative w-full min-w-0 max-w-full">
      <span
        ref={measureRef}
        aria-hidden
        className="uic-drawer-bill-id pointer-events-none absolute m-0 h-0 overflow-hidden whitespace-nowrap p-0 opacity-0"
      >
        {billId}
      </span>
      <div className="flex w-full min-w-0 max-w-full flex-col items-stretch gap-2">
        <span className={`uic-drawer-bill-id block w-full min-w-0 ${idClass}`}>
          {billId}
        </span>
        <StateDrawerStatusPill bill={bill} />
      </div>
    </div>
  );
}
