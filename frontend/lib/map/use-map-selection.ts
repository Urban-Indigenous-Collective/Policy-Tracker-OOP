"use client";

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useMemo } from "react";

import { normalizeStateRouteParam } from "@/lib/api/state-code";

const STATE_PATH = /^\/states\/([A-Za-z]{2})\/?$/;

function stateFromPath(pathname: string | null): string | null {
  const match = pathname?.match(STATE_PATH);
  return match ? normalizeStateRouteParam(match[1]) : null;
}

/** Drawer + map highlight follow the URL only (no optimistic override). */
export function useMapSelection() {
  const pathname = usePathname();
  const router = useRouter();
  const selectedState = useMemo(() => stateFromPath(pathname), [pathname]);

  const selectState = useCallback(
    (code: string | null) => {
      if (code) {
        router.replace(`/states/${code}`, { scroll: false });
      } else {
        router.replace("/", { scroll: false });
      }
    },
    [router],
  );

  const onMapStateClick = useCallback(
    (code: string) => {
      if (selectedState === code) {
        selectState(null);
      } else {
        selectState(code);
      }
    },
    [selectState, selectedState],
  );

  const closeState = useCallback(() => {
    selectState(null);
  }, [selectState]);

  return { selectedState, onMapStateClick, closeState };
}
