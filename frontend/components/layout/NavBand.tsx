/** Wider band — Figma navigation inset (desktop). */
export function NavBand({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`w-full px-page-x sm:px-page-x-md lg:px-nav-inset ${className}`.trim()}
    >
      {children}
    </div>
  );
}
