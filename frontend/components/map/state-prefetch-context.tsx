"use client";

import {
  createContext,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useQueryClient } from "@tanstack/react-query";

import { publicApiKeys } from "@/lib/api/query-keys";
import type {
  PublicBillDetailResponse,
  PublicStateBillsResponse,
} from "@/lib/api/types";

type StatePrefetch = {
  state: string;
  bills: PublicStateBillsResponse;
};

type BillDetailPrefetch = {
  state: string;
  slug: string;
  detail: PublicBillDetailResponse;
};

type StatePrefetchContextValue = {
  prefetch: StatePrefetch | null;
  setPrefetch: (value: StatePrefetch | null) => void;
  billDetail: BillDetailPrefetch | null;
  setBillDetail: (value: BillDetailPrefetch | null) => void;
};

const StatePrefetchContext = createContext<StatePrefetchContextValue | null>(
  null,
);

export function StatePrefetchProvider({ children }: { children: ReactNode }) {
  const [prefetch, setPrefetch] = useState<StatePrefetch | null>(null);
  const [billDetail, setBillDetail] = useState<BillDetailPrefetch | null>(null);
  const value = useMemo(
    () => ({ prefetch, setPrefetch, billDetail, setBillDetail }),
    [billDetail, prefetch],
  );
  return (
    <StatePrefetchContext.Provider value={value}>
      {children}
    </StatePrefetchContext.Provider>
  );
}

export function useStatePrefetch() {
  const ctx = useContext(StatePrefetchContext);
  if (!ctx) {
    throw new Error("useStatePrefetch must be used within StatePrefetchProvider");
  }
  return ctx;
}

/** Mounted by `/states/[code]` page to pass SSR bill list into the map shell. */
export function StatePrefetchSetter({
  stateCode,
  data,
}: {
  stateCode: string;
  data: PublicStateBillsResponse | null;
}) {
  const { setPrefetch } = useStatePrefetch();

  useLayoutEffect(() => {
    if (data) {
      setPrefetch({ state: stateCode, bills: data });
    } else {
      setPrefetch(null);
    }
    return () => setPrefetch(null);
  }, [data, setPrefetch, stateCode]);

  return null;
}

/** Mounted by `/states/[code]/bills/[slug]` so a deep link can paint the panel. */
export function BillDetailPrefetchSetter({
  stateCode,
  slug,
  detail,
}: {
  stateCode: string;
  slug: string;
  detail: PublicBillDetailResponse;
}) {
  const { setBillDetail } = useStatePrefetch();
  const queryClient = useQueryClient();

  useLayoutEffect(() => {
    queryClient.setQueryData(publicApiKeys.bill(detail.bill.id), detail);
    setBillDetail({ state: stateCode, slug, detail });
    return () => setBillDetail(null);
  }, [detail, queryClient, setBillDetail, slug, stateCode]);

  return null;
}
