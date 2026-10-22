import { billStatusVariant } from "@/lib/bill/status-variant";
import type { PublicBill } from "@/lib/api/types";

const pillClass: Record<
  ReturnType<typeof billStatusVariant>,
  string
> = {
  passed: "border-accent text-accent",
  failed: "border-status-failed text-status-failed",
  pending: "border-status-pending text-status-pending",
  neutral: "border-muted text-muted",
};

type StateDrawerStatusPillProps = {
  bill: PublicBill;
  /** When true, pill spans the bill id stack (min `--width-drawer-status-pill`). */
  matchStackWidth?: boolean;
  /** Widen pill equally on both sides (stack width unchanged). */
  extendLeft?: boolean;
};

export function StateDrawerStatusPill({
  bill,
  matchStackWidth = false,
  extendLeft = false,
}: StateDrawerStatusPillProps) {
  const label = bill.status?.trim() || bill.progression?.trim();
  if (!label) return null;

  const variant = billStatusVariant(bill);

  const widthClass = extendLeft
    ? "uic-drawer-status-pill-extend-left min-w-0"
    : matchStackWidth
      ? "w-full min-w-0 max-w-full"
      : "inline-flex w-drawer-status-pill max-w-full";

  return (
    <span
      className={`flex h-drawer-status-pill shrink-0 items-center justify-center overflow-hidden rounded-[30px] border bg-transparent px-1 text-center text-drawer-status-pill font-sans font-semibold leading-none uppercase tracking-label ${widthClass} ${pillClass[variant]}`}
    >
      {label}
    </span>
  );
}
