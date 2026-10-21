/** Centers the Figma artboard max width on wide viewports. */
export function ShellWidth({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`mx-auto w-full max-w-artboard ${className}`.trim()}>
      {children}
    </div>
  );
}
