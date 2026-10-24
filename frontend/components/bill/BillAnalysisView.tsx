"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { StatusBadge } from "@/components/ui/StatusBadge";
import type { PublicBill } from "@/lib/api/types";
import {
  countSearchMatchesInText,
  HighlightSearchText,
} from "@/lib/bill/highlight-search-text";
import {
  billStatusFocusRingClass,
  billStatusIconLinkClass,
  billStatusLinkClass,
  billStatusPillClass,
  billStatusTextClass,
  type BillStatusVariant,
} from "@/lib/bill/status-classes";
import { billStatusVariant } from "@/lib/bill/status-variant";
import { DRAWER_EVAL_FILTERS } from "@/lib/state/drawer-eval-filters";
import { useDrawerReveal } from "@/lib/state/drawer-motion";

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
  labelVariant,
  children,
}: {
  label: string;
  variant?: "summary" | "meta";
  labelVariant?: "summary" | "meta";
  children: ReactNode;
}) {
  const resolvedLabelVariant = labelVariant ?? variant;
  const rowClass =
    variant === "meta"
      ? "uic-bill-detail-row"
      : "uic-bill-detail-row uic-bill-detail-row--summary";
  return (
    <div className={rowClass}>
      <DetailGridLabel variant={resolvedLabelVariant}>{label}</DetailGridLabel>
      <DetailGridBody variant={variant}>{children}</DetailGridBody>
    </div>
  );
}

function TextRow({
  label,
  body,
  labelVariant,
  searchQuery,
}: {
  label: string;
  body: string | undefined;
  labelVariant?: "summary" | "meta";
  searchQuery: string;
}) {
  if (!body?.trim()) return null;
  return (
    <DetailRow label={label} labelVariant={labelVariant}>
      <HighlightSearchText text={body} query={searchQuery} />
    </DetailRow>
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
  label: ReactNode;
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

function BillSearchIcon() {
  return (
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
  );
}

function BillInlineContentSearch({
  searchOpen,
  onToggle,
  searchFieldId,
  statusVariant,
  value,
  onChange,
  onKeyDown,
  matchSummary,
  matchSummaryId,
}: {
  searchOpen: boolean;
  onToggle: () => void;
  searchFieldId: string;
  statusVariant: BillStatusVariant;
  value: string;
  onChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
  matchSummary: string;
  matchSummaryId: string;
}) {
  const { mounted, revealed, revealStyle, onRevealTransitionEnd } =
    useDrawerReveal(searchOpen);
  const focusRing = billStatusFocusRingClass[statusVariant];
  const showPillChrome = searchOpen || mounted;

  useEffect(() => {
    if (!revealed) return;
    const id = window.requestAnimationFrame(() => {
      document.getElementById(searchFieldId)?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(id);
  }, [revealed, searchFieldId]);

  const toggleButton = (
    <button
      type="button"
      aria-expanded={searchOpen}
      aria-controls={searchFieldId}
      aria-label={searchOpen ? "Close search in bill" : "Search within bill"}
      onClick={onToggle}
      className={
        showPillChrome
          ? `inline-flex h-bill-pill shrink-0 cursor-pointer items-center justify-center px-1 outline-none hover:opacity-80 focus-visible:ring-2 ${billStatusFocusRingClass[statusVariant]}`
          : `inline-flex h-bill-pill shrink-0 cursor-pointer items-center justify-center ${billStatusIconLinkClass(statusVariant)}`
      }
    >
      <BillSearchIcon />
    </button>
  );

  if (!showPillChrome) {
    return toggleButton;
  }

  return (
    <div className="inline-flex max-w-full min-w-0 items-center gap-bill-pill-gap">
      <div
        className={`inline-flex h-bill-pill min-w-0 items-center overflow-hidden rounded-bill-pill border uic-bill-pill ${billStatusPillClass[statusVariant]}`}
      >
        {toggleButton}
        {mounted ? (
          <div
            className="overflow-hidden transition-[max-width,opacity] motion-reduce:transition-none"
            style={{
              ...revealStyle,
              maxWidth: revealed
                ? "var(--width-bill-inline-search)"
                : "0px",
              opacity: revealed ? 1 : 0,
            }}
            onTransitionEnd={onRevealTransitionEnd}
          >
            <label htmlFor={searchFieldId} className="sr-only">
              Find text in this bill
            </label>
            <input
              id={searchFieldId}
              type="search"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Find in bill…"
              autoComplete="off"
              enterKeyHint="search"
              tabIndex={revealed ? 0 : -1}
              aria-hidden={!revealed}
              aria-describedby={matchSummary ? matchSummaryId : undefined}
              className={`uic-bill-inline-search-input h-bill-pill w-bill-inline-search min-w-0 appearance-none border-0 bg-transparent pr-bill-inline-search-x pl-bill-inline-search-x outline-none focus-visible:ring-1 ${focusRing}`}
            />
          </div>
        ) : null}
      </div>
      {revealed && matchSummary ? (
        <p
          id={matchSummaryId}
          className="shrink-0 text-bill-pill leading-bill-pill text-muted tabular-nums"
          aria-live="polite"
        >
          {matchSummary}
        </p>
      ) : (
        <span id={matchSummaryId} className="sr-only" aria-live="polite">
          {matchSummary}
        </span>
      )}
    </div>
  );
}

function syncActiveSearchMatch(
  root: HTMLElement | null,
  query: string,
  activeMatchIndex: number,
): void {
  if (!root || !query.trim()) return;
  const marks = root.querySelectorAll<HTMLElement>("[data-bill-search-match]");
  marks.forEach((el) => el.removeAttribute("data-bill-search-active"));
  if (marks.length === 0) return;
  const index =
    ((activeMatchIndex % marks.length) + marks.length) % marks.length;
  const active = marks[index];
  active.setAttribute("data-bill-search-active", "");
  active.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function billSearchableTexts(
  bill: PublicBill,
  evalJustifications: { body: string }[],
  meta: {
    progression?: string;
    chamber?: string;
    session?: string;
    lastUpdate?: string;
    reviewStatus?: string;
    categoriesLabel?: string;
  },
): string[] {
  const texts = [
    bill.summary,
    bill.uicPros,
    bill.uicCons,
    ...evalJustifications.map((row) => row.body),
    meta.progression,
    meta.chamber,
    meta.session,
    meta.lastUpdate,
    meta.reviewStatus,
    meta.categoriesLabel,
  ];
  if (bill.billTextUrl?.trim()) texts.push("Open bill text");
  if (bill.optionalLink?.trim()) texts.push("Open link");
  if (bill.billOverviewUrl?.trim()) texts.push("View official overview");
  return texts.map((t) => t?.trim()).filter(Boolean) as string[];
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

  const searchFieldId = useId();
  const matchSummaryId = useId();
  const contentRef = useRef<HTMLDivElement>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeMatchIndex, setActiveMatchIndex] = useState(0);

  const hasMetadata =
    Boolean(progression) ||
    Boolean(chamber) ||
    Boolean(session) ||
    Boolean(lastUpdate) ||
    Boolean(reviewStatus) ||
    categories.length > 0 ||
    Boolean(bill.billTextUrl?.trim()) ||
    Boolean(bill.optionalLink?.trim()) ||
    Boolean(bill.billOverviewUrl?.trim());

  const categoriesLabel =
    categories.length > 0 ? categories.join(", ") : undefined;

  const matchCount = searchQuery.trim()
    ? billSearchableTexts(bill, evalJustifications, {
        progression,
        chamber,
        session,
        lastUpdate,
        reviewStatus,
        categoriesLabel,
      }).reduce(
        (total, text) => total + countSearchMatchesInText(text, searchQuery),
        0,
      )
    : 0;

  const safeActiveIndex =
    matchCount > 0
      ? ((activeMatchIndex % matchCount) + matchCount) % matchCount
      : 0;

  useLayoutEffect(() => {
    syncActiveSearchMatch(contentRef.current, searchQuery, safeActiveIndex);
  }, [searchQuery, safeActiveIndex, matchCount]);

  const matchSummary = !searchQuery.trim()
    ? ""
    : matchCount === 0
      ? "No matches"
      : `${safeActiveIndex + 1} of ${matchCount}`;

  function handleSearchChange(value: string) {
    setSearchQuery(value);
    setActiveMatchIndex(0);
  }

  function toggleSearch() {
    setSearchOpen((open) => {
      if (open) {
        setSearchQuery("");
        setActiveMatchIndex(0);
      }
      return !open;
    });
  }

  function handleSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      setSearchOpen(false);
      setSearchQuery("");
      setActiveMatchIndex(0);
      return;
    }
    if (event.key === "Enter" && searchQuery.trim()) {
      event.preventDefault();
      setActiveMatchIndex((index) => (event.shiftKey ? index - 1 : index + 1));
    }
  }

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

      <div className="mt-bill-pills-mt">
        <div className="flex flex-wrap items-center gap-bill-pill-gap">
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
          <BillInlineContentSearch
            searchOpen={searchOpen}
            onToggle={toggleSearch}
            searchFieldId={searchFieldId}
            statusVariant={statusVariant}
            value={searchQuery}
            onChange={handleSearchChange}
            onKeyDown={handleSearchKeyDown}
            matchSummary={matchSummary}
            matchSummaryId={matchSummaryId}
          />
        </div>
      </div>

      <div ref={contentRef}>
        <div className="uic-bill-detail-grid mt-bill-summary-mt">
          <TextRow label="Summary" body={bill.summary} searchQuery={searchQuery} />
          <TextRow label="Pros" body={bill.uicPros} searchQuery={searchQuery} />
          <TextRow label="Cons" body={bill.uicCons} searchQuery={searchQuery} />
        </div>

        {evalJustifications.length > 0 ? (
          <div className="uic-bill-detail-grid mt-bill-summary-mt">
            {evalJustifications.map((row) => (
              <TextRow
                key={row.key}
                label={row.label}
                body={row.body}
                labelVariant="meta"
                searchQuery={searchQuery}
              />
            ))}
          </div>
        ) : null}

        {hasMetadata ? (
          <div className="uic-bill-detail-grid uic-bill-detail-grid--meta mt-bill-summary-mt">
            {progression ? (
              <MetaRow label="Progression">
                <HighlightSearchText text={progression} query={searchQuery} />
              </MetaRow>
            ) : null}
            {chamber ? (
              <MetaRow label="Chamber">
                <HighlightSearchText text={chamber} query={searchQuery} />
              </MetaRow>
            ) : null}
            {session ? (
              <MetaRow label="Session">
                <HighlightSearchText text={session} query={searchQuery} />
              </MetaRow>
            ) : null}
            {lastUpdate ? (
              <MetaRow label="Last update">
                <HighlightSearchText text={lastUpdate} query={searchQuery} />
              </MetaRow>
            ) : null}
            {reviewStatus ? (
              <MetaRow label="Review status">
                <HighlightSearchText text={reviewStatus} query={searchQuery} />
              </MetaRow>
            ) : null}
            {categories.length > 0 ? (
              <MetaRow label="Categories">
                <HighlightSearchText text={categories.join(", ")} query={searchQuery} />
              </MetaRow>
            ) : null}
            {bill.billTextUrl?.trim() ? (
              <MetaRow label="Bill text">
                <ExternalLink
                  href={bill.billTextUrl.trim()}
                  label={
                    <HighlightSearchText text="Open bill text" query={searchQuery} />
                  }
                  statusVariant={statusVariant}
                />
              </MetaRow>
            ) : null}
            {bill.optionalLink?.trim() ? (
              <MetaRow label="Optional link">
                <ExternalLink
                  href={bill.optionalLink.trim()}
                  label={<HighlightSearchText text="Open link" query={searchQuery} />}
                  statusVariant={statusVariant}
                />
              </MetaRow>
            ) : null}
            {bill.billOverviewUrl?.trim() ? (
              <MetaRow label="Bill overview">
                <ExternalLink
                  href={bill.billOverviewUrl.trim()}
                  label={
                    <HighlightSearchText
                      text="View official overview"
                      query={searchQuery}
                    />
                  }
                  statusVariant={statusVariant}
                />
              </MetaRow>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}
