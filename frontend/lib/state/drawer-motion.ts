"use client";

import {
  useCallback,
  useLayoutEffect,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type TransitionEvent,
} from "react";

/** Shared with the state drawer and the bill panel that slides out of it. */
export const DRAWER_SLIDE_IN_MS = 440;
export const DRAWER_SLIDE_OUT_MS = 340;

/** In: accelerates, slight overshoot at rest. Out: ease-in — lingers then exits fast. */
export const DRAWER_SLIDE_IN_EASE = "cubic-bezier(0.38, 0, 0.52, 1.38)";
export const DRAWER_SLIDE_OUT_EASE = "cubic-bezier(0.72, 0, 0.98, 0.35)";

export function drawerSlideStyle(slideIn: boolean): CSSProperties {
  return {
    transitionDuration: slideIn
      ? `${DRAWER_SLIDE_IN_MS}ms`
      : `${DRAWER_SLIDE_OUT_MS}ms`,
    transitionTimingFunction: slideIn
      ? DRAWER_SLIDE_IN_EASE
      : DRAWER_SLIDE_OUT_EASE,
  };
}

function subscribePrefersReducedMotion(onChange: () => void) {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

function getPrefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribePrefersReducedMotion,
    getPrefersReducedMotion,
    () => false,
  );
}

/**
 * Keeps a panel mounted through the slide-out, then clears `activeKey`.
 * A new key while already open swaps content without replaying the slide.
 */
export function useDrawerSlide(openKey: string | null) {
  const reduceMotion = usePrefersReducedMotion();
  const [activeKey, setActiveKey] = useState<string | null>(openKey);
  const [slideIn, setSlideIn] = useState(false);
  const [wasOpen, setWasOpen] = useState(false);
  const [prevOpenKey, setPrevOpenKey] = useState<string | null | undefined>(
    undefined,
  );
  const [prevReduceMotion, setPrevReduceMotion] = useState<boolean | undefined>(
    undefined,
  );
  const [enterNonce, setEnterNonce] = useState(0);

  if (openKey !== prevOpenKey || reduceMotion !== prevReduceMotion) {
    setPrevOpenKey(openKey);
    setPrevReduceMotion(reduceMotion);
    if (openKey) {
      setActiveKey(openKey);
      if (wasOpen || reduceMotion) {
        setSlideIn(true);
      } else {
        setSlideIn(false);
        setEnterNonce((n) => n + 1);
      }
      setWasOpen(true);
    } else if (reduceMotion) {
      setSlideIn(false);
      setActiveKey(null);
      setWasOpen(false);
    } else {
      setSlideIn(false);
    }
  }

  useLayoutEffect(() => {
    if (!openKey || slideIn || reduceMotion) return;
    const id = requestAnimationFrame(() => setSlideIn(true));
    return () => cancelAnimationFrame(id);
  }, [openKey, slideIn, reduceMotion, enterNonce]);

  const onSlideTransitionEnd = useCallback(
    (event: TransitionEvent<HTMLElement>) => {
      if (reduceMotion || openKey) return;
      if (event.target !== event.currentTarget) return;
      // Tailwind v4 moves `translate-*` on the `translate` property, not `transform`.
      if (event.propertyName !== "transform" && event.propertyName !== "translate") {
        return;
      }
      setActiveKey(null);
      setWasOpen(false);
    },
    [openKey, reduceMotion],
  );

  return { activeKey, slideIn, onSlideTransitionEnd };
}

/** Same durations/easing as drawer slide — for width/opacity reveals (e.g. inline search). */
export function drawerRevealStyle(revealed: boolean): CSSProperties {
  return drawerSlideStyle(revealed);
}

/**
 * Mount → reveal on open; hide → unmount on close (matches drawer slide-out timing).
 */
export function useDrawerReveal(open: boolean) {
  const reduceMotion = usePrefersReducedMotion();
  const [mounted, setMounted] = useState(open);
  const [revealed, setRevealed] = useState(false);
  const [wasOpen, setWasOpen] = useState(false);
  const [prevOpen, setPrevOpen] = useState<boolean | undefined>(undefined);
  const [prevReduceMotion, setPrevReduceMotion] = useState<boolean | undefined>(
    undefined,
  );
  const [enterNonce, setEnterNonce] = useState(0);

  if (open !== prevOpen || reduceMotion !== prevReduceMotion) {
    setPrevOpen(open);
    setPrevReduceMotion(reduceMotion);
    if (open) {
      setMounted(true);
      if (wasOpen || reduceMotion) {
        setRevealed(true);
      } else {
        setRevealed(false);
        setEnterNonce((n) => n + 1);
      }
      setWasOpen(true);
    } else if (reduceMotion) {
      setRevealed(false);
      setMounted(false);
      setWasOpen(false);
    } else {
      setRevealed(false);
    }
  }

  useLayoutEffect(() => {
    if (!open || revealed || reduceMotion) return;
    const id = requestAnimationFrame(() => setRevealed(true));
    return () => cancelAnimationFrame(id);
  }, [open, revealed, reduceMotion, enterNonce]);

  const onRevealTransitionEnd = useCallback(
    (event: TransitionEvent<HTMLElement>) => {
      if (reduceMotion || open) return;
      if (event.target !== event.currentTarget) return;
      if (
        event.propertyName !== "max-width" &&
        event.propertyName !== "opacity"
      ) {
        return;
      }
      setMounted(false);
      setWasOpen(false);
    },
    [open, reduceMotion],
  );

  return {
    mounted,
    revealed,
    revealStyle: drawerRevealStyle(revealed),
    onRevealTransitionEnd,
  };
}
