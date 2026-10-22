import type { ReactNode } from "react";

import { StatusBadge } from "@/components/ui/StatusBadge";
import type { PublicBill } from "@/lib/api/types";
import { billStatusVariant } from "@/lib/bill/status-variant";
import { DRAWER_EVAL_FILTERS } from "@/lib/state/drawer-eval-filters";

type BillAnalysisViewProps = {
  bill: PublicBill;
};

function DetailGridLabel({
  children,
  variant = "summary",
}: {
  children: string;
  variant?: "summary" | "meta";
}) {
  const className =
    variant === "summary"
      ? "uic-bill-summary-label text-bill-summary-label font-bold leading-bill-summary-label"
      : "uic-bill-meta-label text-bill-title font-bold leading-bill-title";
  return <h2 className={className}>{children}</h2>;
}

function DetailGridBody({
  children,
  variant = "summary",
}: {
  children: ReactNode;
  variant?: "summary" | "meta";
}) {
  const className =
    variant === "summary" ? "uic-bill-summary-body" : "uic-bill-meta-body";
  return <div className={className}>{children}</div>;
}

function TextRow({
  label,
  body,
}: {
  label: string;
  body: string | undefined;
}) {
  if (!body?.trim()) return null;
  return (
    <>
      <DetailGridLabel>{label}</DetailGridLabel>
      <DetailGridBody>{body}</DetailGridBody>
    </>
  );
}

function MetaRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <>
      <DetailGridLabel variant="meta">{label}</DetailGridLabel>
      <DetailGridBody variant="meta">{children}</DetailGridBody>
    </>
  );
}

function ExternalLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent underline decoration-accent/40 underline-offset-2 outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-accent"
    >
      {label}
    </a>
  );
}

function OverviewSearchLink({ href }: { href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="View official bill overview"
      className="inline-flex h-bill-pill shrink-0 items-center justify-center text-accent outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-accent"
    >
      <svg
        width={18}
        height={18}
        viewBox="0 0 512 512"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="size-bill-search shrink-0"
        aria-hidden
      >
        <path
          d="M368 192c0 79.5-64.5 144-144 144S80 271.5 80 192 144.5 48 224 48s144 64.5 144 144z"
          stroke="currentColor"
          strokeWidth={32}
        />
        <path
          d="M337 337 448 448"
          stroke="currentColor"
          strokeWidth={32}
          strokeLinecap="round"
        />
      </svg>
    </a>
  );
}

export function BillAnalysisView({ bill }: BillAnalysisViewProps) {
  const billNumber = bill.billNumber?.trim();
  const name = bill.name?.trim();
  const hero = billNumber || name || "Policy analysis";
  const subtitle = billNumber && name && name !== billNumber ? name : "";
  const statusLabel = bill.status?.trim();
  const progression = bill.progression?.trim();
  const chamber = bill.chamber?.trim();
  const session = bill.session?.trim();
  const lastUpdate = bill.lastUpdate?.trim();
  const reviewStatus = bill.reviewStatus?.trim();
  const categories = (bill.categories ?? []).map((c) => String(c).trim()).filter(Boolean);
  const evalAnswers = DRAWER_EVAL_FILTERS.flatMap((filter) => {
    const answer = bill[filter.key]?.trim();
    if (!answer) return [];
    return [{ key: filter.key, label: filter.label, answer }];
  });

  const hasMetadata =
    Boolean(progression) ||
    Boolean(chamber) ||
    Boolean(session) ||
    Boolean(lastUpdate) ||
    Boolean(reviewStatus) ||
    categories.length > 0 ||
    Boolean(bill.billTextUrl?.trim()) ||
    Boolean(bill.optionalLink?.trim());

  return (
    <article className="w-full max-w-bill-panel pb-section-sm">
      <header className="mt-bill-number-mt">
        <h1
          className={
            billNumber
              ? "uic-bill-number text-bill-number font-semibold leading-bill-number tracking-bill-number text-accent"
              : "uic-bill-title text-bill-title font-medium leading-bill-title"
          }
        >
          {hero}
        </h1>
        {subtitle ? (
          <p className="uic-bill-title mt-bill-title-mt">{subtitle}</p>
        ) : null}
      </header>

      <div className="mt-bill-pills-mt flex flex-wrap items-center gap-bill-pill-gap">
        {statusLabel ? (
          <StatusBadge variant={billStatusVariant(bill)}>{statusLabel}</StatusBadge>
        ) : null}
        {evalAnswers.map((item) => (
          <span
            key={item.key}
            className="uic-bill-pill rounded-bill-pill border border-accent px-bill-pill-x text-bill-pill font-semibold leading-bill-pill text-accent lg:h-bill-pill"
          >
            {item.label}: {item.answer}
          </span>
        ))}
        {bill.billOverviewUrl ? (
          <OverviewSearchLink href={bill.billOverviewUrl} />
        ) : null}
      </div>

      <div className="uic-bill-detail-grid mt-bill-summary-mt">
        <TextRow label="Summary" body={bill.summary} />
        <TextRow label="Pros" body={bill.uicPros} />
        <TextRow label="Cons" body={bill.uicCons} />
      </div>

      {hasMetadata ? (
        <div className="uic-bill-detail-grid uic-bill-detail-grid--meta mt-bill-summary-mt">
          {progression ? (
            <MetaRow label="Progression">
              <span>{progression}</span>
            </MetaRow>
          ) : null}
          {chamber ? (
            <MetaRow label="Chamber">
              <span>{chamber}</span>
            </MetaRow>
          ) : null}
          {session ? (
            <MetaRow label="Session">
              <span>{session}</span>
            </MetaRow>
          ) : null}
          {lastUpdate ? (
            <MetaRow label="Last update">
              <span>{lastUpdate}</span>
            </MetaRow>
          ) : null}
          {reviewStatus ? (
            <MetaRow label="Review status">
              <span>{reviewStatus}</span>
            </MetaRow>
          ) : null}
          {categories.length > 0 ? (
            <MetaRow label="Categories">
              <span>{categories.join(", ")}</span>
            </MetaRow>
          ) : null}
          {bill.billTextUrl?.trim() ? (
            <MetaRow label="Bill text">
              <ExternalLink href={bill.billTextUrl.trim()} label="Open bill text" />
            </MetaRow>
          ) : null}
          {bill.optionalLink?.trim() ? (
            <MetaRow label="Optional link">
              <ExternalLink href={bill.optionalLink.trim()} label="Open link" />
            </MetaRow>
          ) : null}
          {bill.billOverviewUrl?.trim() ? (
            <MetaRow label="Bill overview">
              <ExternalLink
                href={bill.billOverviewUrl.trim()}
                label="View official overview"
              />
            </MetaRow>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
