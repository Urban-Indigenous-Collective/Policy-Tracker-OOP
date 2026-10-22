import { fetchPublicStates, fetchStateBills } from "@/lib/api/client";
import { isSvgMapStateCode } from "@/lib/api/state-code";
import { absoluteUrl } from "@/lib/seo/site-url";

export type SitemapEntry = {
  url: string;
  lastModified?: Date;
};

/** All indexable public routes: home, state hubs, and Live bill analysis pages. */
export async function collectPublicSitemapEntries(): Promise<SitemapEntry[]> {
  const entries: SitemapEntry[] = [{ url: absoluteUrl("/") }];

  let statesPayload;
  try {
    statesPayload = await fetchPublicStates({ base: "server" });
  } catch {
    return entries;
  }

  const lastModified = statesPayload.generatedAt
    ? new Date(statesPayload.generatedAt)
    : undefined;

  const stateCodes = new Set<string>(Object.keys(statesPayload.states ?? {}));

  for (const code of stateCodes) {
    if (!isSvgMapStateCode(code)) continue;

    let billsPayload;
    try {
      billsPayload = await fetchStateBills(code, { base: "server" });
    } catch {
      continue;
    }

    if (isSvgMapStateCode(code)) {
      entries.push({
        url: absoluteUrl(`/states/${code}`),
        lastModified: billsPayload.generatedAt
          ? new Date(billsPayload.generatedAt)
          : lastModified,
      });
    }

    for (const bill of billsPayload.bills) {
      if (!bill.slug) continue;
      const billState = bill.state?.trim().toUpperCase() || code;
      if (!isSvgMapStateCode(billState)) continue;
      entries.push({
        url: absoluteUrl(`/states/${billState}/bills/${bill.slug}`),
        lastModified: billsPayload.generatedAt
          ? new Date(billsPayload.generatedAt)
          : lastModified,
      });
    }
  }

  return entries;
}
