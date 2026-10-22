"use client";

import { useEffect, useId, useRef } from "react";

import { StateBillList } from "@/components/state/StateBillList";
import { useStateBills } from "@/lib/api/hooks";
import type { PublicStateBillsResponse } from "@/lib/api/types";
import { STATE_NAMES } from "@/lib/map/state-codes";

type StatePanelProps = {
  stateCode: string;
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
  onClose,
  initialBills = null,
  slideIn = true,
  slideInDurationMs = 440,
  slideOutDurationMs = 340,
  onSlideTransitionEnd,
}: StatePanelProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
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

  const name = STATE_NAMES[stateCode] ?? stateCode;

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
      className={`fixed inset-y-0 right-0 z-[110] flex w-full max-w-[28rem] flex-col border-l border-surface-border bg-background shadow-2xl outline-none transition-transform motion-reduce:transition-none ${
        slideIn ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <header className="flex shrink-0 items-start justify-between gap-4 border-b border-surface-border px-5 py-4">
        <div>
          <p className="font-mono text-label-xs tracking-label text-muted">
            STATE LEGISLATION
          </p>
          <h2 id={titleId} className="mt-1 font-sans text-body font-bold text-foreground">
            {name}
            <span className="ml-2 font-mono text-body-sm font-bold text-accent">
              {stateCode}
            </span>
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded border border-surface-border px-3 py-1.5 font-mono text-label-xs tracking-label text-foreground hover:bg-surface-hover"
        >
          CLOSE
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {isLoading && !data ? (
          <p className="font-mono text-body-sm text-muted" aria-live="polite">
            Loading policies…
          </p>
        ) : null}
        {isError ? (
          <p className="text-sm text-red-400" role="alert">
            {error instanceof Error ? error.message : "Could not load bills."}
          </p>
        ) : null}
        {data ? (
          <StateBillList stateCode={stateCode} bills={data.bills} />
        ) : null}
      </div>
    </aside>
  );
}
