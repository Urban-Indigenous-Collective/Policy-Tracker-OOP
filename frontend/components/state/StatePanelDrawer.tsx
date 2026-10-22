"use client";

import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type TransitionEvent,
} from "react";

import { StatePanel } from "@/components/state/StatePanel";
import type { PublicStateBillsResponse } from "@/lib/api/types";
import type { LegendCategory } from "@/lib/map/legend";

const SLIDE_IN_MS = 440;
const SLIDE_OUT_MS = 340;

type StatePanelDrawerProps = {
  stateCode: string | null;
  stateCategories: Record<string, LegendCategory>;
  onClose: () => void;
  initialBills?: PublicStateBillsResponse | null;
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useLayoutEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

/** Keeps the panel mounted through the slide-out, then unmounts. */
export function StatePanelDrawer({
  stateCode,
  stateCategories,
  onClose,
  initialBills = null,
}: StatePanelDrawerProps) {
  const reduceMotion = usePrefersReducedMotion();
  const [activeCode, setActiveCode] = useState<string | null>(stateCode);
  const [slideIn, setSlideIn] = useState(false);
  const wasOpenRef = useRef(false);

  useLayoutEffect(() => {
    if (stateCode) {
      setActiveCode(stateCode);
      if (wasOpenRef.current) {
        setSlideIn(true);
      } else if (reduceMotion) {
        setSlideIn(true);
      } else {
        setSlideIn(false);
        const id = requestAnimationFrame(() => setSlideIn(true));
        wasOpenRef.current = true;
        return () => cancelAnimationFrame(id);
      }
      wasOpenRef.current = true;
      return;
    }

    if (reduceMotion) {
      setSlideIn(false);
      setActiveCode(null);
      wasOpenRef.current = false;
      return;
    }

    setSlideIn(false);
  }, [reduceMotion, stateCode]);

  const onSlideTransitionEnd = useCallback(
    (event: TransitionEvent<HTMLElement>) => {
      if (reduceMotion || stateCode) return;
      if (event.propertyName !== "transform") return;
      setActiveCode(null);
      wasOpenRef.current = false;
    },
    [reduceMotion, stateCode],
  );

  if (!activeCode) return null;

  return (
    <StatePanel
      stateCode={activeCode}
      stateCategory={stateCategories[activeCode]}
      onClose={onClose}
      initialBills={activeCode === stateCode ? initialBills : null}
      slideIn={slideIn}
      slideInDurationMs={SLIDE_IN_MS}
      slideOutDurationMs={SLIDE_OUT_MS}
      onSlideTransitionEnd={onSlideTransitionEnd}
    />
  );
}
