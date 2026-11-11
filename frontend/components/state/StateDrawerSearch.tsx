"use client";

import { useEffect, type KeyboardEvent } from "react";

import { useDrawerReveal } from "@/lib/state/drawer-motion";

type StateDrawerSearchProps = {
  value: string;
  onChange: (value: string) => void;
  id?: string;
  label?: string;
  className?: string;
};

function DrawerSearchIcon() {
  return (
    <svg
      width={18}
      height={18}
      viewBox="0 0 512 512"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="size-bill-search shrink-0"
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
  );
}

type DrawerSearchFieldProps = {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  label: string;
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void;
  /** Toolbar inline field: input only (icon is the separate toggle). */
  inputOnly?: boolean;
  tabIndex?: number;
  ariaHidden?: boolean;
};

function DrawerSearchField({
  id,
  value,
  onChange,
  label,
  onKeyDown,
  inputOnly = false,
  tabIndex,
  ariaHidden,
}: DrawerSearchFieldProps) {
  return (
    <>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      {!inputOnly ? (
        <div className="relative h-drawer-search w-full overflow-hidden rounded-drawer-search bg-drawer-search">
          <span
            className="pointer-events-none absolute top-0 left-drawer-search-icon-inset flex h-full w-[18px] items-center justify-center text-foreground"
            aria-hidden
          >
            <DrawerSearchIcon />
          </span>
          <input
            id={id}
            type="search"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="search"
            autoComplete="off"
            enterKeyHint="search"
            tabIndex={tabIndex}
            aria-hidden={ariaHidden}
            className="uic-drawer-search-input h-drawer-search w-full appearance-none border-0 bg-transparent pr-4 pl-drawer-search-text-inset outline-none focus-visible:ring-1 focus-visible:ring-foreground/25"
          />
        </div>
      ) : (
        <input
          id={id}
          type="search"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="search"
          autoComplete="off"
          enterKeyHint="search"
          tabIndex={tabIndex}
          aria-hidden={ariaHidden}
          className="uic-drawer-search-input h-drawer-search w-full min-w-0 appearance-none border-0 bg-transparent pr-4 pl-2 outline-none focus-visible:ring-1 focus-visible:ring-foreground/25"
        />
      )}
    </>
  );
}

/** Figma `239:6757`–`239:6759` — pill field, FA-style icon + “search” placeholder. */
export function StateDrawerSearch({
  value,
  onChange,
  id,
  label = "Search policies in this state",
  className = "",
}: StateDrawerSearchProps) {
  return (
    <div
      className={`mt-drawer-search-mt w-full max-w-drawer-content ${className}`.trim()}
    >
      <DrawerSearchField
        id={id}
        value={value}
        onChange={onChange}
        label={label}
      />
    </div>
  );
}

type StateDrawerToolbarSearchProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: string;
  onChange: (value: string) => void;
  id: string;
  label?: string;
};

/** Policy list toolbar (`202:6591`): icon toggles drawer-style search pill inline in the control row. */
export function StateDrawerToolbarSearch({
  open,
  onOpenChange,
  value,
  onChange,
  id,
  label = "Search policies",
}: StateDrawerToolbarSearchProps) {
  const { mounted, revealed, revealStyle, onRevealTransitionEnd } =
    useDrawerReveal(open);
  const showPill = open || mounted;

  useEffect(() => {
    if (!revealed) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(id)?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [revealed, id]);

  const toggleButton = (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={id}
      aria-label={open ? "Close search" : "Open search"}
      onClick={() => onOpenChange(!open)}
      className={
        showPill
          ? "flex h-drawer-search w-[var(--spacing-drawer-search-text-inset)] shrink-0 cursor-pointer items-center justify-center text-foreground outline-none transition-opacity hover:opacity-70 focus-visible:ring-2 focus-visible:ring-accent"
          : "flex size-bill-search shrink-0 cursor-pointer items-center justify-center text-foreground outline-none transition-opacity hover:opacity-70 focus-visible:ring-2 focus-visible:ring-accent"
      }
    >
      <DrawerSearchIcon />
    </button>
  );

  if (!showPill) {
    return toggleButton;
  }

  return (
    <div className="inline-flex max-w-drawer-content min-w-0 items-center">
      <div className="inline-flex h-drawer-search min-w-0 items-center overflow-hidden rounded-drawer-search bg-drawer-search">
        {toggleButton}
        {mounted ? (
          <div
            className="overflow-hidden transition-[max-width,opacity] motion-reduce:transition-none"
            style={{
              ...revealStyle,
              maxWidth: revealed
                ? "calc(var(--width-drawer-search) - var(--spacing-drawer-search-text-inset))"
                : "0px",
              opacity: revealed ? 1 : 0,
            }}
            onTransitionEnd={onRevealTransitionEnd}
          >
            <DrawerSearchField
              id={id}
              value={value}
              onChange={onChange}
              label={label}
              inputOnly
              tabIndex={revealed ? 0 : -1}
              ariaHidden={!revealed}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
