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
};

export function StateDrawerStatusPill({ bill }: StateDrawerStatusPillProps) {
  const label = bill.status?.trim() || bill.progression?.trim();
  if (!label) return null;

  const variant = billStatusVariant(bill);

  return (
    <span
      className={`inline-flex h-drawer-status-pill w-drawer-status-pill shrink-0 items-center justify-center overflow-hidden rounded-[30px] border bg-transparent px-1 text-drawer-status-pill font-sans font-semibold uppercase tracking-label ${pillClass[variant]}`}
    >
      {label}
    </span>
  );
}
