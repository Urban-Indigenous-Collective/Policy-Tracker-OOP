"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { useCallback, useMemo } from "react";

import {
  isSvgMapStateCode,
  normalizeStateRouteParam,
} from "@/lib/api/state-code";

const STATE_PATH = /^\/states\/([A-Za-z]{2})\/?$/;

function stateFromPath(pathname: string | null): string | null {
  const match = pathname?.match(STATE_PATH);
  if (!match) return null;
  const code = normalizeStateRouteParam(match[1]);
  return isSvgMapStateCode(code) ? code : null;
}

function stateFromRouteParams(
  params: ReturnType<typeof useParams>,
): string | null {
  const raw = params.code;
  if (typeof raw !== "string") return null;
  const code = normalizeStateRouteParam(raw);
  return isSvgMapStateCode(code) ? code : null;
}

/** Drawer + map highlight follow the URL only (no optimistic override). */
export function useMapSelection() {
  const pathname = usePathname();
  const params = useParams();
  const router = useRouter();
  const selectedState = useMemo(
    () => stateFromPath(pathname) ?? stateFromRouteParams(params),
    [pathname, params],
  );

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
