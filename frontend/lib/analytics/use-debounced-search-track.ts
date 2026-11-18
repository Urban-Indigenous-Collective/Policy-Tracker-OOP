"use client";

import { useEffect, useRef } from "react";

import {
  trackSearchSubmit,
  type SearchContext,
} from "@/lib/analytics/events";

const DEFAULT_DEBOUNCE_MS = 800;

/**
 * Fires `search_submit` after the query stays non-empty for `debounceMs`.
 * Clears the timer when the query is emptied.
 */
export function useDebouncedSearchTrack(
  query: string,
  context: SearchContext,
  options?: { stateCode?: string; debounceMs?: number },
): void {
  const stateCode = options?.stateCode;
  const debounceMs = options?.debounceMs ?? DEFAULT_DEBOUNCE_MS;
  const lastSent = useRef("");

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      lastSent.current = "";
      return;
    }
    if (trimmed === lastSent.current) return;

    const timer = window.setTimeout(() => {
      lastSent.current = trimmed;
      trackSearchSubmit({
        context,
        queryLength: trimmed.length,
        stateCode,
      });
    }, debounceMs);

    return () => window.clearTimeout(timer);
  }, [query, context, stateCode, debounceMs]);
}
