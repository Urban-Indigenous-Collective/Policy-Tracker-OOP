/**
 * Push custom events to the GTM dataLayer (GA4 tags listen in Tag Manager).
 * No-ops when GTM is unset or window is unavailable (SSR).
 * Every event includes `surface` (`embed` | `site`) for GA segments.
 */

import { resolveAnalyticsSurface } from "@/lib/analytics/surface";

export type DataLayerEvent = {
  event: string;
  [key: string]: string | number | boolean | undefined;
};

declare global {
  interface Window {
    dataLayer?: Record<string, unknown>[];
  }
}

/** Short window to collapse React Strict Mode double-effects in dev. */
const recentKeys = new Map<string, number>();
const DEDUPE_MS = 400;

function shouldSend(dedupeKey: string | undefined): boolean {
  if (!dedupeKey) return true;
  const now = Date.now();
  const prev = recentKeys.get(dedupeKey);
  if (prev != null && now - prev < DEDUPE_MS) return false;
  recentKeys.set(dedupeKey, now);
  return true;
}

export function trackEvent(
  event: string,
  params: Record<string, string | number | boolean | undefined> = {},
  options?: { dedupeKey?: string },
): void {
  if (typeof window === "undefined") return;
  if (!shouldSend(options?.dedupeKey)) return;

  const payload: DataLayerEvent = {
    event,
    surface: resolveAnalyticsSurface(),
    ...params,
  };
  window.dataLayer = window.dataLayer ?? [];
  window.dataLayer.push(payload);
}
