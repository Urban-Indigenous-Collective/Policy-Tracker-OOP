/**
 * Narrower main band — Figma content inset 123px (desktop), extra right
 * room for the map legend (~256px to artboard edge).
 */
export function ContentBand({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`w-full px-5 sm:px-8 lg:px-[123px] lg:pr-[76px] ${className}`.trim()}
    >
      {children}
    </div>
  );
}
