import Link from "next/link";

import { StatusBadge } from "@/components/ui/StatusBadge";
import { billStatusVariant } from "@/lib/bill/status-variant";
import type { PublicBill } from "@/lib/api/types";
import { STATE_NAMES } from "@/lib/map/state-codes";

type BillAnalysisViewProps = {
  bill: PublicBill;
  stateCode: string;
};

function AnalysisBlock({
  title,
  body,
}: {
  title: string;
  body: string | undefined;
}) {
  if (!body?.trim()) return null;
  return (
    <section className="mt-section border-t border-surface-border pt-section-sm">
      <h2 className="font-mono text-label-xs tracking-label text-accent">
        {title}
      </h2>
      <div className="mt-3 whitespace-pre-wrap text-body-sm leading-body-sm text-foreground-muted">
        {body}
      </div>
    </section>
  );
}

export function BillAnalysisView({ bill, stateCode }: BillAnalysisViewProps) {
  const stateName = STATE_NAMES[stateCode] ?? stateCode;
  const title = bill.name || bill.billNumber || "Policy analysis";

  return (
    <article className="pb-section-sm">
      <nav className="mb-section-sm">
        <Link
          href={`/states/${stateCode}`}
          className="font-mono text-label-xs tracking-label text-accent hover:underline"
        >
          ← Back to {stateName}
        </Link>
      </nav>

      <header>
        <p className="font-mono text-label-xs tracking-label text-muted">
          {stateName} · {stateCode}
        </p>
        <h1 className="mt-2 font-sans text-hero-fluid font-bold leading-hero text-foreground">
          {title}
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {bill.status ? (
            <StatusBadge variant={billStatusVariant(bill)}>
              {bill.status}
            </StatusBadge>
          ) : null}
          {bill.progression ? (
            <span className="font-mono text-label-xs text-muted">
              {bill.progression}
            </span>
          ) : null}
        </div>
        {(bill.billNumber || bill.session) && (
          <p className="mt-2 font-mono text-body-sm text-muted">
            {[bill.billNumber, bill.session].filter(Boolean).join(" · ")}
          </p>
        )}
        {bill.lastUpdate ? (
          <p className="mt-1 text-body-sm text-muted">
            Last update: {bill.lastUpdate}
          </p>
        ) : null}
      </header>

      {bill.summary ? (
        <section className="mt-section">
          <h2 className="font-mono text-label-xs tracking-label text-accent">
            SUMMARY
          </h2>
          <p className="mt-3 text-body-sm leading-body-sm text-foreground-muted">
            {bill.summary}
          </p>
        </section>
      ) : null}

      <AnalysisBlock title="UIC PROS" body={bill.uicPros} />
      <AnalysisBlock title="UIC CONS" body={bill.uicCons} />

      {bill.billOverviewUrl ? (
        <p className="mt-section">
          <a
            href={bill.billOverviewUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-label-xs tracking-label text-accent underline-offset-2 hover:underline"
          >
            VIEW OFFICIAL BILL OVERVIEW
          </a>
        </p>
      ) : null}
    </article>
  );
}
