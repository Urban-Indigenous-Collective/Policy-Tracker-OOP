import type { StatusBadgeProps } from "@/components/ui/StatusBadge";

export type BillStatusVariant = NonNullable<StatusBadgeProps["variant"]>;

/** Text color for bill id / hero — matches drawer status pill semantics. */
export const billStatusTextClass: Record<BillStatusVariant, string> = {
  passed: "text-accent",
  failed: "text-status-failed",
  pending: "text-status-pending",
  neutral: "text-muted",
};

/** Outline pill border + text — same scale as `StateDrawerStatusPill`. */
export const billStatusPillClass: Record<BillStatusVariant, string> = {
  passed: "border-accent text-accent",
  failed: "border-status-failed text-status-failed",
  pending: "border-status-pending text-status-pending",
  neutral: "border-muted text-muted",
};

/** Underline decoration for status-colored external links. */
export const billStatusLinkDecorationClass: Record<BillStatusVariant, string> = {
  passed: "decoration-accent/40",
  failed: "decoration-status-failed/40",
  pending: "decoration-status-pending/40",
  neutral: "decoration-muted/40",
};

/** Focus ring for status-colored interactive chrome (links, icon buttons). */
export const billStatusFocusRingClass: Record<BillStatusVariant, string> = {
  passed: "focus-visible:ring-accent",
  failed: "focus-visible:ring-status-failed",
  pending: "focus-visible:ring-status-pending",
  neutral: "focus-visible:ring-muted",
};

const billStatusInteractiveBase =
  "outline-none hover:opacity-80 focus-visible:ring-2";

/** Text link styling paired with `billStatusTextClass`. */
export function billStatusLinkClass(variant: BillStatusVariant): string {
  return `${billStatusTextClass[variant]} underline ${billStatusLinkDecorationClass[variant]} underline-offset-2 ${billStatusInteractiveBase} ${billStatusFocusRingClass[variant]}`;
}

/** Icon / compact link styling paired with `billStatusTextClass`. */
export function billStatusIconLinkClass(variant: BillStatusVariant): string {
  return `${billStatusTextClass[variant]} ${billStatusInteractiveBase} ${billStatusFocusRingClass[variant]}`;
}
