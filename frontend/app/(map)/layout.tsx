import { Suspense } from "react";

import { MapExperience } from "@/components/map/MapExperience";
import { MapExperienceFallback } from "@/components/map/MapExperienceFallback";
import { fetchPublicStates } from "@/lib/api/client";

/** TanStack Query uses time during render; defer static prerender of map shell. */
export const instant = false;

export default async function MapRouteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  let initialStates = null;
  try {
    initialStates = await fetchPublicStates({ base: "server" });
  } catch {
    // Client will refetch.
  }

  return (
    <Suspense fallback={<MapExperienceFallback />}>
      <MapExperience initialStates={initialStates}>{children}</MapExperience>
    </Suspense>
  );
}
