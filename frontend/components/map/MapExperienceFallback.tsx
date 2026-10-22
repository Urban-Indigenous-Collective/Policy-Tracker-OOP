/** Shown while map client tree (TanStack Query) suspends during prerender. */
export function MapExperienceFallback() {
  return (
    <div className="pb-map-content-pb" aria-busy="true" aria-label="Loading map">
      <div className="min-h-[12rem] w-full animate-pulse rounded bg-white/[0.04]" />
    </div>
  );
}
