/**
 * Product analytics → GA4.
 *
 * Always pushes to the GTM dataLayer. Also calls `gtag('event', …)` when the
 * GTM GA4 Config tag has installed gtag, so custom events reach GA4 without
 * needing dozens of GTM Data Layer variables / GA4 Event tags.
 */

import { resolveAnalyticsSurface } from "@/lib/analytics/surface";

export type DataLayerEvent = {
  event: string;
  [key: string]: string | number | boolean | undefined;
};

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
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

function cleanParams(
  params: Record<string, string | number | boolean | undefined>,
): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) out[key] = value;
  }
  return out;
}

/** Send via gtag now, or briefly retry while GTM finishes loading GA4. */
function sendViaGtag(
  event: string,
  params: Record<string, string | number | boolean>,
  transportType?: "beacon",
): void {
  const gtagParams =
    transportType === "beacon"
      ? { ...params, transport_type: "beacon" as const }
      : params;

  const fire = () => {
    if (typeof window.gtag !== "function") return false;
    window.gtag("event", event, gtagParams);
    return true;
  };
  if (fire()) return;

  let tries = 0;
  const timer = window.setInterval(() => {
    tries += 1;
    if (fire() || tries >= 20) window.clearInterval(timer);
  }, 250);
}

export function trackEvent(
  event: string,
  params: Record<string, string | number | boolean | undefined> = {},
  options?: { dedupeKey?: string; /** Use for clicks that navigate away immediately. */ beacon?: boolean },
): void {
  if (typeof window === "undefined") return;
  if (!shouldSend(options?.dedupeKey)) return;

  const eventParams = cleanParams({
    surface: resolveAnalyticsSurface(),
    ...params,
  });

  const payload: DataLayerEvent = { event, ...eventParams };
  window.dataLayer = window.dataLayer ?? [];
  window.dataLayer.push(payload);

  sendViaGtag(event, eventParams, options?.beacon ? "beacon" : undefined);
}
