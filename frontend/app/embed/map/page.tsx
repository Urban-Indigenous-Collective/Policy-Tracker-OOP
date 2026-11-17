import type { Metadata } from "next";
import { Suspense } from "react";

import { MapExperience } from "@/components/map/MapExperience";
import { MapExperienceFallback } from "@/components/map/MapExperienceFallback";
import { fetchPublicStates } from "@/lib/api/client";

export const instant = false;

export const metadata: Metadata = {
  title: "MMIP map embed",
  description:
    "Embeddable MMIP policy map — status counts, choropleth, legend, and legislation filters.",
  robots: { index: false, follow: false },
};

/** Stats + map + legend + layer toggles (no site chrome, no intro hero). */
export default async function EmbedMapPage() {
  let initialStates = null;
  try {
    initialStates = await fetchPublicStates({ base: "server" });
  } catch {
    // Client will refetch.
  }

  return (
    <Suspense fallback={<MapExperienceFallback />}>
      <MapExperience initialStates={initialStates} variant="embed" />
    </Suspense>
  );
}
