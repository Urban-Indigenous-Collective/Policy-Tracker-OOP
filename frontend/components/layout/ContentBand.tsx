/**
 * Main content band — Figma content inset (desktop), extra right gutter for
 * map legend on wide layouts.
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
      className={`w-full px-page-x sm:px-page-x-md lg:px-content-inset lg:pr-content-gutter-right ${className}`.trim()}
    >
      {children}
    </div>
  );
}
