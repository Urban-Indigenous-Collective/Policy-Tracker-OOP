import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { StatePrefetchSetter } from "@/components/map/state-prefetch-context";
import { fetchStateBills } from "@/lib/api/client";
import { isSvgMapStateCode, normalizeStateRouteParam } from "@/lib/api/state-code";
import { STATE_NAMES } from "@/lib/map/state-codes";
import { absoluteUrl } from "@/lib/seo/site-url";

export const instant = false;

type PageProps = {
  params: Promise<{ code: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { code: raw } = await params;
  const code = normalizeStateRouteParam(raw);
  if (!isSvgMapStateCode(code)) {
    return { title: "State not found | MMIP Policy Tracker" };
  }
  const name = STATE_NAMES[code] ?? code;
  const path = `/states/${code}`;
  const description = `Live MMIP-related legislation and UIC policy analysis for ${name} (${code}).`;
  return {
    title: `${name} (${code})`,
    description,
    alternates: { canonical: absoluteUrl(path) },
    openGraph: {
      title: `${name} MMIP policies`,
      description,
      url: absoluteUrl(path),
    },
  };
}

export default async function StateMapPage({ params }: PageProps) {
  const { code: raw } = await params;
  const code = normalizeStateRouteParam(raw);

  if (!isSvgMapStateCode(code)) {
    notFound();
  }

  let initialStateBills = null;
  try {
    initialStateBills = await fetchStateBills(code, { base: "server" });
  } catch {
    // Client will refetch.
  }

  return (
    <StatePrefetchSetter stateCode={code} data={initialStateBills} />
  );
}
