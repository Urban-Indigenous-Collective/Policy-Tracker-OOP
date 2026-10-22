"use client";

type FilterToggleProps = {
  active: boolean;
  onToggle: () => void;
  label: string;
  id?: string;
};

/** Figma Filter switch (46×21): knob inset 3px; on = left, off = right. */
export function FilterToggle({ active, onToggle, label, id }: FilterToggleProps) {
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={active}
      aria-label={label}
      onClick={onToggle}
      className="flex min-w-0 max-w-full cursor-pointer items-center gap-filter-switch-gap rounded-md border-0 bg-transparent p-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-accent 2xl:shrink-0"
    >
      <span
        aria-hidden
        className={`box-border inline-flex h-[var(--size-switch-h)] w-[var(--size-switch-w)] shrink-0 items-center rounded-full border border-foreground p-[0.1875rem] ${
          active ? "justify-start" : "justify-end"
        }`}
      >
        <span
          className={`size-[0.9375rem] shrink-0 rounded-full bg-accent transition-opacity duration-200 motion-reduce:transition-none ${
            active ? "opacity-100" : "opacity-inactive"
          }`}
        />
      </span>
      <span className="uic-label whitespace-nowrap text-foreground">{label}</span>
    </button>
  );
}
