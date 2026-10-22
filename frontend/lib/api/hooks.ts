"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchBillById,
  fetchPublicStates,
  fetchStateBills,
} from "@/lib/api/client";
import { PUBLIC_QUERY_STALE_MS, publicApiKeys } from "@/lib/api/query-keys";
import type {
  PublicStateBillsResponse,
  PublicStatesResponse,
} from "@/lib/api/types";

type QueryInitialOptions<T> = {
  initialData?: T | null;
};

export function usePublicStates(options?: QueryInitialOptions<PublicStatesResponse>) {
  const initialData = options?.initialData ?? undefined;
  return useQuery({
    queryKey: publicApiKeys.states(),
    queryFn: () => fetchPublicStates(),
    initialData: initialData ?? undefined,
    staleTime: PUBLIC_QUERY_STALE_MS,
    refetchOnWindowFocus: false,
  });
}

export function useStateBills(
  code: string | null,
  options?: QueryInitialOptions<PublicStateBillsResponse>,
) {
  const normalized = code?.trim().toUpperCase() ?? "";
  const initialData = options?.initialData ?? undefined;
  return useQuery({
    queryKey: publicApiKeys.stateBills(normalized),
    queryFn: () => fetchStateBills(normalized),
    enabled: Boolean(normalized),
    initialData: initialData ?? undefined,
    staleTime: PUBLIC_QUERY_STALE_MS,
    refetchOnWindowFocus: false,
  });
}

export function useBillDetail(recordId: string | null) {
  const id = recordId?.trim() ?? "";
  return useQuery({
    queryKey: publicApiKeys.bill(id),
    queryFn: () => fetchBillById(id),
    enabled: Boolean(id),
    staleTime: PUBLIC_QUERY_STALE_MS,
    refetchOnWindowFocus: false,
  });
}
