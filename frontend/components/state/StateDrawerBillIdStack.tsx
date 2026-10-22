"use client";

import { useLayoutEffect, useRef, useState } from "react";

import { StateDrawerStatusPill } from "@/components/state/StateDrawerStatusPill";
import type { PublicBill } from "@/lib/api/types";

type StateDrawerBillIdStackProps = {
  billId: string;
  bill: PublicBill;
};

type StackLayout = "compact" | "wide" | "wrapped";

const PILL_WIDTH_REM = 6.5625;
const ID_COL_WIDTH_REM = 9.875;

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
  if (chars > 14) return "wrapped";
  if (chars > 8) return "wide";
  return "compact";
}

/**
 * Bill id + status pill share one width.
 * - compact: fixed Figma pill width (default bills).
 * - wide: id wider than pill but fits the id column (e.g. EO 13898).
 * - wrapped: id wider than the column; text breaks inside the column, pill spans column.
 */
export function StateDrawerBillIdStack({ billId, bill }: StateDrawerBillIdStackProps) {
  const measureRef = useRef<HTMLSpanElement>(null);
  const [layout, setLayout] = useState<StackLayout>(() => initialLayout(billId));

  useLayoutEffect(() => {
    const measure = measureRef.current;
    if (!measure) return;

    const intrinsic = measure.getBoundingClientRect().width;
    const pillPx = cssVarRemToPx("--width-drawer-status-pill", PILL_WIDTH_REM);
    const colPx = cssVarRemToPx("--width-drawer-bill-col-id", ID_COL_WIDTH_REM);

    if (intrinsic > colPx + 0.5) setLayout("wrapped");
    else if (intrinsic > pillPx + 0.5) setLayout("wide");
    else setLayout("compact");
  }, [billId]);

  const stackClass =
    layout === "wrapped"
      ? "flex w-full min-w-0 max-w-full flex-col items-stretch gap-2"
      : layout === "wide"
        ? "inline-flex w-max max-w-[var(--width-drawer-bill-col-id)] min-w-drawer-status-pill flex-col items-stretch gap-2"
        : "inline-flex w-drawer-status-pill shrink-0 flex-col items-stretch gap-2 overflow-visible";

  const idClass =
    layout === "wrapped"
      ? "uic-drawer-bill-id-constrained text-left"
      : layout === "wide"
        ? "uic-drawer-bill-id-constrained uic-drawer-bill-id-centered"
        : "uic-drawer-bill-id-centered";

  return (
    <div className="relative min-w-0 max-w-full">
      <span
        ref={measureRef}
        aria-hidden
        className="uic-drawer-bill-id pointer-events-none absolute m-0 h-0 overflow-hidden whitespace-nowrap p-0 opacity-0"
      >
        {billId}
      </span>
      <div className={stackClass}>
        <span className={`uic-drawer-bill-id block w-full min-w-0 ${idClass}`}>
          {billId}
        </span>
        <StateDrawerStatusPill
          bill={bill}
          matchStackWidth
          extendLeft={layout !== "wrapped"}
        />
      </div>
    </div>
  );
}
