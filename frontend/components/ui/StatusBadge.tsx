export type StatusBadgeProps = {
  children: React.ReactNode;
  variant?: "passed" | "failed" | "pending" | "neutral";
};

const variantClass: Record<NonNullable<StatusBadgeProps["variant"]>, string> = {
  passed: "border-accent/60 bg-accent/10 text-accent",
  failed: "border-muted bg-white/5 text-muted",
  pending:
    "border-status-pending/60 bg-status-pending/10 text-status-pending",
  neutral: "border-white/20 bg-white/5 text-foreground",
};

export function StatusBadge({
  children,
  variant = "neutral",
}: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center justify-center rounded px-3 py-1 text-label-xs font-bold tracking-wide ${variantClass[variant]}`}
    >
      {children}
    </span>
  );
}
