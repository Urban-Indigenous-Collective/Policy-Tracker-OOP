"use client";

import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
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

export function usePrefersReducedMotion(): boolean {
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

/**
 * Keeps a panel mounted through the slide-out, then clears `activeKey`.
 * A new key while already open swaps content without replaying the slide.
 */
export function useDrawerSlide(openKey: string | null) {
  const reduceMotion = usePrefersReducedMotion();
  const [activeKey, setActiveKey] = useState<string | null>(openKey);
  const [slideIn, setSlideIn] = useState(false);
  const wasOpenRef = useRef(false);

  useLayoutEffect(() => {
    if (openKey) {
      setActiveKey(openKey);
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
      setActiveKey(null);
      wasOpenRef.current = false;
      return;
    }

    setSlideIn(false);
  }, [openKey, reduceMotion]);

  const onSlideTransitionEnd = useCallback(
    (event: TransitionEvent<HTMLElement>) => {
      if (reduceMotion || openKey) return;
      if (event.target !== event.currentTarget) return;
      // Tailwind v4 moves `translate-*` on the `translate` property, not `transform`.
      if (event.propertyName !== "transform" && event.propertyName !== "translate") {
        return;
      }
      setActiveKey(null);
      wasOpenRef.current = false;
    },
    [openKey, reduceMotion],
  );

  return { activeKey, slideIn, onSlideTransitionEnd };
}
