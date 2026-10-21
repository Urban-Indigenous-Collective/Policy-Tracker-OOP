/** Wider band — Figma Navigation inset 76px (desktop). */
export function NavBand({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`w-full px-5 sm:px-8 lg:px-[76px] ${className}`.trim()}>
      {children}
    </div>
  );
}
