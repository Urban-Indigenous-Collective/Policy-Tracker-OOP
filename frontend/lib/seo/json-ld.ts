import type { PublicBill } from "@/lib/api/types";
import { STATE_NAMES } from "@/lib/map/state-codes";

import { absoluteUrl } from "@/lib/seo/site-url";

const ORG_NAME = "Urban Indigenous Collective";
const SITE_NAME = "MMIP Policy Tracker";

export function organizationJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: ORG_NAME,
    url: absoluteUrl("/"),
  };
}

export function webSiteJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: absoluteUrl("/"),
    description:
      "Interactive map and analysis of U.S. state and federal policies addressing Missing and Murdered Indigenous Persons (MMIP / MMIWGT2S).",
    publisher: {
      "@type": "Organization",
      name: ORG_NAME,
      url: absoluteUrl("/"),
    },
  };
}

export function billAnalysisJsonLd(bill: PublicBill, stateCode: string) {
  const stateName = STATE_NAMES[stateCode] ?? stateCode;
  const name = bill.name || bill.billNumber || "Policy";
  const path = `/states/${stateCode}/bills/${bill.slug}`;
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: name,
    description: bill.summary?.slice(0, 500) || undefined,
    url: absoluteUrl(path),
    identifier: bill.billNumber || bill.id,
    about: {
      "@type": "AdministrativeArea",
      name: stateName,
    },
    isPartOf: {
      "@type": "WebSite",
      name: SITE_NAME,
      url: absoluteUrl("/"),
    },
  };
}
