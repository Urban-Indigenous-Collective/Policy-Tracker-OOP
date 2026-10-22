import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { StatePrefetchSetter } from "@/components/map/state-prefetch-context";
import { fetchStateBills } from "@/lib/api/client";
import { isSvgMapStateCode, normalizeStateRouteParam } from "@/lib/api/state-code";
import { STATE_NAMES } from "@/lib/map/state-codes";

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
  const base = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  const path = `/states/${code}`;
  return {
    title: `${name} (${code}) | MMIP Policy Tracker`,
    description: `Live MMIP-related legislation and policy analysis for ${name}.`,
    alternates: base ? { canonical: `${base}${path}` } : undefined,
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
