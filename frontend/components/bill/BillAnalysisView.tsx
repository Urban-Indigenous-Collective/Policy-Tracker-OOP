import type { ReactNode } from "react";

import { StatusBadge } from "@/components/ui/StatusBadge";
import type { PublicBill } from "@/lib/api/types";
import {
  billStatusIconLinkClass,
  billStatusLinkClass,
  billStatusPillClass,
  billStatusTextClass,
  type BillStatusVariant,
} from "@/lib/bill/status-classes";
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
    variant === "summary" ? "uic-bill-summary-label" : "uic-bill-meta-label";
  return <div className={className}>{children}</div>;
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

function DetailRow({
  label,
  variant = "summary",
  children,
}: {
  label: string;
  variant?: "summary" | "meta";
  children: ReactNode;
}) {
  const rowClass =
    variant === "meta"
      ? "uic-bill-detail-row"
      : "uic-bill-detail-row uic-bill-detail-row--summary";
  return (
    <div className={rowClass}>
      <DetailGridLabel variant={variant}>{label}</DetailGridLabel>
      <DetailGridBody variant={variant}>{children}</DetailGridBody>
    </div>
  );
}

function TextRow({
  label,
  body,
}: {
  label: string;
  body: string | undefined;
}) {
  if (!body?.trim()) return null;
  return <DetailRow label={label}>{body}</DetailRow>;
}

function MetaRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <DetailRow variant="meta" label={label}>
      {children}
    </DetailRow>
  );
}

function ExternalLink({
  href,
  label,
  statusVariant,
}: {
  href: string;
  label: string;
  statusVariant: BillStatusVariant;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={billStatusLinkClass(statusVariant)}
    >
      {label}
    </a>
  );
}

function OverviewSearchLink({
  href,
  statusVariant,
}: {
  href: string;
  statusVariant: BillStatusVariant;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="View official bill overview"
      className={`inline-flex h-bill-pill shrink-0 items-center justify-center ${billStatusIconLinkClass(statusVariant)}`}
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
  const statusLabel = bill.status?.trim() || bill.progression?.trim();
  const statusVariant = billStatusVariant(bill);
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
  const evalJustifications = DRAWER_EVAL_FILTERS.flatMap((filter) => {
    const body = bill[filter.justificationKey]?.trim();
    if (!body) return [];
    return [{ key: filter.justificationKey, label: filter.justificationLabel, body }];
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
              ? `uic-bill-number text-bill-number font-semibold leading-bill-number tracking-bill-number ${billStatusTextClass[statusVariant]}`
              : "uic-bill-title text-bill-title font-medium leading-bill-title text-foreground"
          }
        >
          {hero}
        </h1>
        {subtitle ? (
          <p className="uic-bill-title mt-bill-title-mt text-foreground">{subtitle}</p>
        ) : null}
      </header>

      <div className="mt-bill-pills-mt flex flex-wrap items-center gap-bill-pill-gap">
        {statusLabel ? (
          <StatusBadge variant={statusVariant}>{statusLabel}</StatusBadge>
        ) : null}
        {evalAnswers.map((item) => (
          <span
            key={item.key}
            className={`uic-bill-pill rounded-bill-pill border px-bill-pill-x text-bill-pill font-semibold leading-bill-pill lg:h-bill-pill ${billStatusPillClass[statusVariant]}`}
          >
            {item.label}: {item.answer}
          </span>
        ))}
        {bill.billOverviewUrl ? (
          <OverviewSearchLink
            href={bill.billOverviewUrl}
            statusVariant={statusVariant}
          />
        ) : null}
      </div>

      <div className="uic-bill-detail-grid mt-bill-summary-mt">
        <TextRow label="Summary" body={bill.summary} />
        <TextRow label="Pros" body={bill.uicPros} />
        <TextRow label="Cons" body={bill.uicCons} />
      </div>

      {evalJustifications.length > 0 ? (
        <div className="uic-bill-detail-grid mt-bill-summary-mt">
          {evalJustifications.map((row) => (
            <TextRow key={row.key} label={row.label} body={row.body} />
          ))}
        </div>
      ) : null}

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
              <ExternalLink
                href={bill.billTextUrl.trim()}
                label="Open bill text"
                statusVariant={statusVariant}
              />
            </MetaRow>
          ) : null}
          {bill.optionalLink?.trim() ? (
            <MetaRow label="Optional link">
              <ExternalLink
                href={bill.optionalLink.trim()}
                label="Open link"
                statusVariant={statusVariant}
              />
            </MetaRow>
          ) : null}
          {bill.billOverviewUrl?.trim() ? (
            <MetaRow label="Bill overview">
              <ExternalLink
                href={bill.billOverviewUrl.trim()}
                label="View official overview"
                statusVariant={statusVariant}
              />
            </MetaRow>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
