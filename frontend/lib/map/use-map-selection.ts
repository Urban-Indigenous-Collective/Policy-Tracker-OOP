"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

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

export type MapSelectionMode = "url" | "local";

/**
 * Drawer + map highlight.
 * - `url` (default): syncs to `/states/...` routes on the full site.
 * - `local`: in-memory only — used by `/embed/map` so iframe clicks stay embedded.
 */
export function useMapSelection(mode: MapSelectionMode = "url") {
  const pathname = usePathname();
  const params = useParams();
  const router = useRouter();
  const [localState, setLocalState] = useState<string | null>(null);
  const [localBillSlug, setLocalBillSlug] = useState<string | null>(null);

  const fromPath = useMemo(() => selectionFromPathname(pathname), [pathname]);
  const urlState = fromPath.stateCode ?? stateFromRouteParams(params);
  const urlBillSlug = fromPath.stateCode ? fromPath.billSlug : null;

  const selectedState = mode === "local" ? localState : urlState;
  const selectedBillSlug = mode === "local" ? localBillSlug : urlBillSlug;

  const selectState = useCallback(
    (code: string | null) => {
      if (mode === "local") {
        setLocalState(code);
        setLocalBillSlug(null);
        return;
      }
      if (code) {
        router.replace(`/states/${stateCodeForUrl(code)}`, { scroll: false });
      } else {
        router.replace("/", { scroll: false });
      }
    },
    [mode, router],
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
    if (mode === "local") {
      setLocalBillSlug(null);
      return;
    }
    if (!selectedState) return;
    router.replace(`/states/${stateCodeForUrl(selectedState)}`, {
      scroll: false,
    });
  }, [mode, router, selectedState]);

  return {
    selectedState,
    selectedBillSlug,
    onMapStateClick,
    closeState,
    closeBill,
    selectState,
  };
}
