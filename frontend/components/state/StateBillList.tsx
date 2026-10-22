import Link from "next/link";

import { StatusBadge } from "@/components/ui/StatusBadge";
import { billStatusVariant } from "@/lib/bill/status-variant";
import type { PublicBill } from "@/lib/api/types";

type StateBillListProps = {
  stateCode: string;
  bills: PublicBill[];
};

export function StateBillList({ stateCode, bills }: StateBillListProps) {
  if (bills.length === 0) {
    return (
      <p className="text-body-sm leading-body-sm text-muted">
        No live policies are published for this state yet.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-4">
      {bills.map((bill) => (
        <li key={bill.id}>
          <Link
            href={`/states/${stateCode}/bills/${bill.slug}`}
            className="group block rounded border border-surface-border bg-white/[0.02] p-4 transition-colors hover:border-accent/40 hover:bg-white/[0.04]"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="font-sans text-body font-semibold text-foreground group-hover:text-accent">
                {bill.name || bill.billNumber || "Untitled bill"}
              </h3>
              {bill.status ? (
                <StatusBadge variant={billStatusVariant(bill)}>
                  {bill.status}
                </StatusBadge>
              ) : null}
            </div>
            {bill.billNumber ? (
              <p className="mt-1 font-mono text-label-xs tracking-label text-muted">
                {bill.billNumber}
                {bill.session ? ` · ${bill.session}` : ""}
              </p>
            ) : null}
            {bill.summary ? (
              <p className="mt-2 line-clamp-3 text-body-sm leading-body-sm text-foreground-muted">
                {bill.summary}
              </p>
            ) : null}
          </Link>
        </li>
      ))}
    </ul>
  );
}
