"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { useCallback, useMemo } from "react";

import {
  isPublicStatePanelCode,
  normalizeStateRouteParam,
  stateCodeForUrl,
} from "@/lib/api/state-code";

const STATE_BILL_PATH = /^\/states\/([^/]+)(?:\/bills\/([^/]+))?\/?$/;

export function selectionFromPathname(pathname: string | null): {
  stateCode: string | null;
  billSlug: string | null;
} {
  const match = pathname?.match(STATE_BILL_PATH);
  if (!match) return { stateCode: null, billSlug: null };
  const code = normalizeStateRouteParam(match[1]);
  if (!isPublicStatePanelCode(code)) return { stateCode: null, billSlug: null };
  const rawSlug = match[2];
  if (!rawSlug) return { stateCode: code, billSlug: null };
  try {
    return { stateCode: code, billSlug: decodeURIComponent(rawSlug) };
  } catch {
    return { stateCode: code, billSlug: rawSlug };
  }
}

function stateFromRouteParams(
  params: ReturnType<typeof useParams>,
): string | null {
  const raw = params.code;
  if (typeof raw !== "string") return null;
  const code = normalizeStateRouteParam(raw);
  return isPublicStatePanelCode(code) ? code : null;
}

/** Drawer + map highlight follow the URL only (no optimistic override). */
export function useMapSelection() {
  const pathname = usePathname();
  const params = useParams();
  const router = useRouter();
  const fromPath = useMemo(() => selectionFromPathname(pathname), [pathname]);
  const selectedState = fromPath.stateCode ?? stateFromRouteParams(params);
  const selectedBillSlug = fromPath.stateCode ? fromPath.billSlug : null;

  const selectState = useCallback(
    (code: string | null) => {
      if (code) {
        router.replace(`/states/${stateCodeForUrl(code)}`, { scroll: false });
      } else {
        router.replace("/", { scroll: false });
      }
    },
    [router],
  );

  const onMapStateClick = useCallback(
    (code: string | null) => {
      if (!code || selectedState === code) {
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

  const closeBill = useCallback(() => {
    if (!selectedState) return;
    router.replace(`/states/${stateCodeForUrl(selectedState)}`, { scroll: false });
  }, [router, selectedState]);

  return {
    selectedState,
    selectedBillSlug,
    onMapStateClick,
    closeState,
    closeBill,
    selectState,
  };
}
