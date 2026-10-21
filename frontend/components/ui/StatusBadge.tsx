type StatusBadgeProps = {
  children: React.ReactNode;
  variant?: "passed" | "failed" | "pending" | "neutral";
};

const variantClass: Record<NonNullable<StatusBadgeProps["variant"]>, string> = {
  passed: "border-accent/60 bg-accent/10 text-accent",
  failed: "border-muted bg-white/5 text-muted",
  pending: "border-[#e8c547]/60 bg-[#e8c547]/10 text-[#e8c547]",
  neutral: "border-white/20 bg-white/5 text-white",
};

export function StatusBadge({
  children,
  variant = "neutral",
}: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center justify-center rounded px-3 py-1 text-xs font-bold tracking-wide ${variantClass[variant]}`}
    >
      {children}
    </span>
  );
}
