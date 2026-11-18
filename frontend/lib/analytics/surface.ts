export type AnalyticsSurface = "embed" | "site";

/** Embed iframes live under `/embed/*`; everything else is the full site. */
export function resolveAnalyticsSurface(
  pathname?: string | null,
): AnalyticsSurface {
  const path =
    pathname ??
    (typeof window !== "undefined" ? window.location.pathname : "");
  return path.startsWith("/embed") ? "embed" : "site";
}
