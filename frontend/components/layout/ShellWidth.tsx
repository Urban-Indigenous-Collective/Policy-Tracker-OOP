/** Centers the 1512px Figma artboard on wide viewports. */
export function ShellWidth({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`mx-auto w-full max-w-[1512px] ${className}`.trim()}>
      {children}
    </div>
  );
}
