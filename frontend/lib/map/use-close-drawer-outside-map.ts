"use client";

import { useEffect } from "react";

const PANEL_ROOT = "[data-mmip-state-panel]";
const STATE_REGION = "[data-state-code]";

/** Close drawer unless the hit is a state shape or the panel (ocean / letterbox closes). */
export function useCloseDrawerOutsideMap(
  selectedState: string | null,
  onClose: () => void,
) {
  useEffect(() => {
    if (!selectedState) return;

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest(PANEL_ROOT)) return;
      if (target.closest(STATE_REGION)) return;
      onClose();
    };

    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [onClose, selectedState]);
}
