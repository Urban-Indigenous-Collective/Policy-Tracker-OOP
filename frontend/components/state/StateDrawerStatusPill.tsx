import { billStatusPillClass } from "@/lib/bill/status-classes";
import { billStatusVariant } from "@/lib/bill/status-variant";
import type { PublicBill } from "@/lib/api/types";

type StateDrawerStatusPillProps = {
  bill: PublicBill;
};

export function StateDrawerStatusPill({ bill }: StateDrawerStatusPillProps) {
  const label = bill.status?.trim() || bill.progression?.trim();
  if (!label) return null;

  const variant = billStatusVariant(bill);

  return (
    <span
      className={`uic-drawer-status-pill flex w-full min-w-0 max-w-full items-center justify-center rounded-[30px] border bg-transparent text-center font-sans font-semibold uppercase tracking-label ${billStatusPillClass[variant]}`}
    >
      {label}
    </span>
  );
}
