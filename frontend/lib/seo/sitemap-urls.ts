import { fetchPublicStates, fetchStateBills } from "@/lib/api/client";
import {
  isPublicStatePanelCode,
  isSvgMapStateCode,
  NATIONAL_STATE_CODE,
  stateCodeForUrl,
} from "@/lib/api/state-code";
import { absoluteUrl } from "@/lib/seo/site-url";

export type SitemapEntry = {
  url: string;
  lastModified?: Date;
};

function dedupeEntries(entries: SitemapEntry[]): SitemapEntry[] {
  const byUrl = new Map<string, SitemapEntry>();
  for (const entry of entries) {
    const existing = byUrl.get(entry.url);
    if (!existing) {
      byUrl.set(entry.url, entry);
      continue;
    }
    if (entry.lastModified && existing.lastModified) {
      if (entry.lastModified > existing.lastModified) {
        byUrl.set(entry.url, entry);
      }
    }
  }
  return [...byUrl.values()];
}

async function appendBillsForJurisdiction(
  entries: SitemapEntry[],
  code: string,
  fallbackModified?: Date,
): Promise<void> {
  let billsPayload;
  try {
    billsPayload = await fetchStateBills(code, { base: "server" });
  } catch {
    return;
  }

  const modified = billsPayload.generatedAt
    ? new Date(billsPayload.generatedAt)
    : fallbackModified;

  if (isPublicStatePanelCode(code)) {
    entries.push({
      url: absoluteUrl(`/states/${stateCodeForUrl(code)}`),
      lastModified: modified,
    });
  }

  for (const bill of billsPayload.bills) {
    if (!bill.slug) continue;
    const billState = bill.state?.trim()
      ? bill.state.trim().toLowerCase() === "national"
        ? NATIONAL_STATE_CODE
        : bill.state.trim().toUpperCase()
      : code;
    if (!isPublicStatePanelCode(billState)) continue;
    entries.push({
      url: absoluteUrl(
        `/states/${stateCodeForUrl(billState)}/bills/${bill.slug}`,
      ),
      lastModified: modified,
    });
  }
}

/** All indexable public routes: home, state/National hubs, and Live bill analysis pages. */
export async function collectPublicSitemapEntries(): Promise<SitemapEntry[]> {
  const entries: SitemapEntry[] = [{ url: absoluteUrl("/") }];

  let statesPayload;
  try {
    statesPayload = await fetchPublicStates({ base: "server" });
  } catch {
    return dedupeEntries(entries);
  }

  const lastModified = statesPayload.generatedAt
    ? new Date(statesPayload.generatedAt)
    : undefined;

  const stateCodes = Object.keys(statesPayload.states ?? {}).filter(
    isSvgMapStateCode,
  );

  for (const code of stateCodes) {
    await appendBillsForJurisdiction(entries, code, lastModified);
  }

  await appendBillsForJurisdiction(entries, NATIONAL_STATE_CODE, lastModified);

  return dedupeEntries(entries);
}
