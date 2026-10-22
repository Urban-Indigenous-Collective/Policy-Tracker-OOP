import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BillAnalysisView } from "@/components/bill/BillAnalysisView";
import { JsonLd } from "@/components/seo/JsonLd";
import { findBillBySlug } from "@/lib/api/bill-utils";
import { fetchBillById, fetchStateBills } from "@/lib/api/client";
import { isSvgMapStateCode, normalizeStateRouteParam } from "@/lib/api/state-code";
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
  if (!isSvgMapStateCode(code)) {
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
    const path = `/states/${code}/bills/${slug}`;
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

  if (!isSvgMapStateCode(code)) {
    notFound();
  }

  let list;
  try {
    list = await fetchStateBills(code, { base: "server" });
  } catch (err) {
    return (
      <div className="pb-section-sm">
        <p className="text-sm text-red-400" role="alert">
          Could not load policy data.{" "}
          {err instanceof Error ? err.message : "Try again later."}
        </p>
        <p className="mt-4">
          <Link
            href={`/states/${code}`}
            className="font-mono text-label-xs text-accent hover:underline"
          >
            Back to state
          </Link>
        </p>
      </div>
    );
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
    return (
      <div className="pb-section-sm">
        <p className="text-sm text-red-400" role="alert">
          Could not load bill analysis.{" "}
          {err instanceof Error ? err.message : "Try again later."}
        </p>
        <p className="mt-4">
          <Link
            href={`/states/${code}`}
            className="font-mono text-label-xs text-accent hover:underline"
          >
            Back to state
          </Link>
        </p>
      </div>
    );
  }

  if (normalizeStateRouteParam(detail.bill.state) !== code) {
    notFound();
  }

  return (
    <>
      <JsonLd data={billAnalysisJsonLd(detail.bill, code)} />
      <BillAnalysisView bill={detail.bill} stateCode={code} />
    </>
  );
}
