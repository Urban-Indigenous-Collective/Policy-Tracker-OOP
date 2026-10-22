"use client";

import {
  createContext,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { PublicStateBillsResponse } from "@/lib/api/types";

type StatePrefetch = {
  state: string;
  bills: PublicStateBillsResponse;
};

type StatePrefetchContextValue = {
  prefetch: StatePrefetch | null;
  setPrefetch: (value: StatePrefetch | null) => void;
};

const StatePrefetchContext = createContext<StatePrefetchContextValue | null>(
  null,
);

export function StatePrefetchProvider({ children }: { children: ReactNode }) {
  const [prefetch, setPrefetch] = useState<StatePrefetch | null>(null);
  const value = useMemo(
    () => ({ prefetch, setPrefetch }),
    [prefetch],
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
