import type { Metadata } from "next";
import { Suspense } from "react";

import { MapExperience } from "@/components/map/MapExperience";
import { MapExperienceFallback } from "@/components/map/MapExperienceFallback";
import { JsonLd } from "@/components/seo/JsonLd";
import { fetchPublicStates } from "@/lib/api/client";
import { organizationJsonLd, webSiteJsonLd } from "@/lib/seo/json-ld";

/** TanStack Query uses time during render; defer static prerender of map shell. */
export const instant = false;

export const metadata: Metadata = {
  title: "Interactive MMIP policy map",
  description:
    "Explore U.S. state legislation on Missing and Murdered Indigenous Persons (MMIP): passed, pending, and failed policies since 2020.",
  alternates: { canonical: "/" },
};

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
    <>
      <JsonLd data={[webSiteJsonLd(), organizationJsonLd()]} />
      <Suspense fallback={<MapExperienceFallback />}>
        <MapExperience initialStates={initialStates}>{children}</MapExperience>
      </Suspense>
    </>
  );
}
