"use client";

type StateDrawerSearchProps = {
  value: string;
  onChange: (value: string) => void;
  id?: string;
};

/** Figma `239:6757`–`239:6759` — pill field, FA-style icon + “search” placeholder. */
export function StateDrawerSearch({ value, onChange, id }: StateDrawerSearchProps) {
  return (
    <div className="mt-drawer-search-mt w-drawer-search max-w-full">
      <label htmlFor={id} className="sr-only">
        Search policies in this state
      </label>
      <div className="relative h-drawer-search w-full overflow-hidden rounded-drawer-search bg-drawer-search">
        <span
          className="pointer-events-none absolute top-0 left-drawer-search-icon-inset flex h-full w-[18px] items-center justify-center text-foreground"
          aria-hidden
        >
          <svg
            width={18}
            height={18}
            viewBox="0 0 512 512"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="size-[18px] shrink-0"
            aria-hidden
          >
            <path
              d="M368 192c0 79.5-64.5 144-144 144S80 271.5 80 192 144.5 48 224 48s144 64.5 144 144z"
              stroke="currentColor"
              strokeWidth={32}
            />
            <path
              d="M337 337 448 448"
              stroke="currentColor"
              strokeWidth={32}
              strokeLinecap="round"
            />
          </svg>
        </span>
        <input
          id={id}
          type="search"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="search"
          autoComplete="off"
          enterKeyHint="search"
          className="uic-drawer-search-input h-drawer-search w-full appearance-none border-0 bg-transparent pr-4 pl-drawer-search-text-inset outline-none focus-visible:ring-1 focus-visible:ring-foreground/25"
        />
      </div>
    </div>
  );
}
