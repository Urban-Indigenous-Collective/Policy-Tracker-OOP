import type { Metadata } from "next";
import { notFound } from "next/navigation";

import {
  BillDetailPrefetchSetter,
  StatePrefetchSetter,
} from "@/components/map/state-prefetch-context";
import { JsonLd } from "@/components/seo/JsonLd";
import { findBillBySlug } from "@/lib/api/bill-utils";
import { fetchBillById, fetchStateBills } from "@/lib/api/client";
import {
  isPublicStatePanelCode,
  normalizeStateRouteParam,
  stateCodeForUrl,
} from "@/lib/api/state-code";
import { billAnalysisJsonLd } from "@/lib/seo/json-ld";
import { absoluteUrl } from "@/lib/seo/site-url";

/** Server fetch for bill detail; not fully static with cacheComponents. */
export const instant = false;

type PageProps = {
  params: Promise<{ code: string; slug: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { code: rawCode, slug } = await params;
  const code = normalizeStateRouteParam(rawCode);
  if (!isPublicStatePanelCode(code)) {
    return { title: "Bill not found | MMIP Policy Tracker" };
  }

  try {
    const list = await fetchStateBills(code, { base: "server" });
    const match = findBillBySlug(list.bills, slug);
    if (!match) {
      return { title: "Bill not found | MMIP Policy Tracker" };
    }
    const detail = await fetchBillById(match.id, { base: "server" });
    const bill = detail.bill;
    const name = bill.name || bill.billNumber || "Policy";
    const path = `/states/${stateCodeForUrl(code)}/bills/${slug}`;
    const description =
      bill.summary?.slice(0, 160) ||
      `UIC policy analysis for ${name} (${code}).`;
    return {
      title: name,
      description,
      alternates: { canonical: absoluteUrl(path) },
      openGraph: {
        title: name,
        description,
        url: absoluteUrl(path),
        type: "article",
      },
    };
  } catch {
    return { title: "Bill | MMIP Policy Tracker" };
  }
}

export default async function BillAnalysisPage({ params }: PageProps) {
  const { code: rawCode, slug } = await params;
  const code = normalizeStateRouteParam(rawCode);

  if (!isPublicStatePanelCode(code)) {
    notFound();
  }

  let list;
  try {
    list = await fetchStateBills(code, { base: "server" });
  } catch {
    return <StatePrefetchSetter stateCode={code} data={null} />;
  }

  const match = findBillBySlug(list.bills, slug);
  if (!match) {
    notFound();
  }

  let detail;
  try {
    detail = await fetchBillById(match.id, { base: "server" });
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("HTTP 404")) {
      notFound();
    }
    return <StatePrefetchSetter stateCode={code} data={list} />;
  }

  if (normalizeStateRouteParam(detail.bill.state) !== code) {
    notFound();
  }

  return (
    <>
      <JsonLd data={billAnalysisJsonLd(detail.bill, code)} />
      <StatePrefetchSetter stateCode={code} data={list} />
      <BillDetailPrefetchSetter stateCode={code} slug={slug} detail={detail} />
    </>
  );
}
