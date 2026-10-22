export type StatusBadgeProps = {
  children: React.ReactNode;
  variant?: "passed" | "failed" | "pending" | "neutral";
};

const variantClass: Record<NonNullable<StatusBadgeProps["variant"]>, string> = {
  passed: "border-status-passed text-status-passed",
  failed: "border-status-failed text-status-failed",
  pending: "border-status-pending text-status-pending",
  neutral: "border-muted text-muted",
};

/** Outline status pill. Colors come from `text-status-*` / `border-status-*`. */
export function StatusBadge({
  children,
  variant = "neutral",
}: StatusBadgeProps) {
  return (
    <span
      className={`uic-bill-pill rounded-bill-pill border px-bill-pill-x text-bill-pill font-semibold leading-bill-pill uppercase lg:h-bill-pill ${variantClass[variant]}`}
    >
      {children}
    </span>
  );
}
