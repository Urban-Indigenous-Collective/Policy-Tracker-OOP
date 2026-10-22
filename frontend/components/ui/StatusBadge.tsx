import { billStatusPillClass } from "@/lib/bill/status-classes";

export type StatusBadgeProps = {
  children: React.ReactNode;
  variant?: "passed" | "failed" | "pending" | "neutral";
};

/** Outline status pill. Colors come from `text-status-*` / `border-status-*`. */
export function StatusBadge({
  children,
  variant = "neutral",
}: StatusBadgeProps) {
  return (
    <span
      className={`uic-bill-pill rounded-bill-pill border px-bill-pill-x text-bill-pill font-semibold leading-bill-pill uppercase lg:h-bill-pill ${billStatusPillClass[variant]}`}
    >
      {children}
    </span>
  );
}
