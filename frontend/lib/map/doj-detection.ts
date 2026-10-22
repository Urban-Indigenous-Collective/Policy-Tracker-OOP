import type { PublicBill } from "@/lib/api/types";

const JUSTICE_GOV =
  /(?:https?:\/\/)?(?:[\w.-]*\.)?justice\.gov(?:\/|$|[?#])/i;

const USAO_NAME =
  /\b(?:USAO|U\.S\.\s*Attorney(?:'s)?\s+Office|United States Attorney)\b/i;

function billUrls(bill: PublicBill): string[] {
  return [bill.billOverviewUrl, bill.optionalLink, bill.billTextUrl].filter(
    (u): u is string => Boolean(u?.trim()),
  );
}

export function urlLooksDojLinked(url: string): boolean {
  const text = url.trim();
  if (!text) return false;
  if (JUSTICE_GOV.test(text)) return true;
  return text.toLowerCase().includes("justice.gov");
}

/** DOJ initiatives = justice.gov on any bill link field, or link-less USAO title rows. */
export function isDojInitiativeBill(bill: PublicBill): boolean {
  for (const url of billUrls(bill)) {
    if (urlLooksDojLinked(url)) return true;
  }
  const billNumber = bill.billNumber?.trim() ?? "";
  const name = bill.name?.trim() ?? "";
  if (!billNumber && name && USAO_NAME.test(name)) return true;
  return false;
}
