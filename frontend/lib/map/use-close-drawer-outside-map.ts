"use client";

import { useEffect } from "react";

const MAP_ROOT = "[data-mmip-usa-map]";
const PANEL_ROOT = "[data-mmip-state-panel]";

/** Close drawer when the user clicks page chrome (not the SVG map or the panel). */
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
      if (target.closest(MAP_ROOT)) return;
      onClose();
    };

    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [onClose, selectedState]);
}
