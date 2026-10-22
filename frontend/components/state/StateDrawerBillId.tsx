"use client";

import { useLayoutEffect, useRef, useState } from "react";

type StateDrawerBillIdProps = {
  children: string;
};

/** Single-line bill numbers centered; left-aligned when wrapped. */
export function StateDrawerBillId({ children }: StateDrawerBillIdProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [wrapped, setWrapped] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const lineHeight = parseFloat(getComputedStyle(el).lineHeight);
    if (!Number.isFinite(lineHeight) || lineHeight <= 0) return;
    const lines = Math.round(el.getBoundingClientRect().height / lineHeight);
    setWrapped(lines > 1);
  }, [children]);

  return (
    <span
      ref={ref}
      className={`uic-drawer-bill-id block w-full ${
        wrapped ? "text-left" : "text-center"
      }`}
    >
      {children}
    </span>
  );
}
