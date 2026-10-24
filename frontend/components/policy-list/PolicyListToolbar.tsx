"use client";

import { useId } from "react";

import {
  StateDrawerFilterButton,
  StateDrawerFilterMenu,
} from "@/components/state/StateDrawerFilter";
import { StateDrawerSearch } from "@/components/state/StateDrawerSearch";
import type { DrawerFilterKey } from "@/lib/state/drawer-eval-filters";

type PolicyListToolbarProps = {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  searchOpen: boolean;
  onSearchOpenChange: (open: boolean) => void;
  evalFilters: DrawerFilterKey[];
  onEvalFiltersChange: (next: DrawerFilterKey[]) => void;
  filtersOpen: boolean;
  onFiltersOpenChange: (open: boolean) => void;
};

export function PolicyListToolbar({
  searchQuery,
  onSearchChange,
  searchOpen,
  onSearchOpenChange,
  evalFilters,
  onEvalFiltersChange,
  filtersOpen,
  onFiltersOpenChange,
}: PolicyListToolbarProps) {
  const filterTrayId = useId();
  const searchId = useId();
  const filtersActive = evalFilters.length > 0;

  return (
    <div className="relative">
      <div className="relative w-full">
        <div className="flex min-h-policy-list-toolbar-row items-center justify-end gap-4">
          <StateDrawerFilterButton
            open={filtersOpen}
            active={filtersActive}
            controlsId={filterTrayId}
            placement="toolbar"
            onToggle={() => onFiltersOpenChange(!filtersOpen)}
          />

          <button
            type="button"
            aria-expanded={searchOpen}
            aria-controls={searchId}
            aria-label={searchOpen ? "Close search" : "Open search"}
            onClick={() => onSearchOpenChange(!searchOpen)}
            className="flex size-bill-search shrink-0 items-center justify-center text-foreground outline-none transition-opacity hover:opacity-70 focus-visible:ring-2 focus-visible:ring-accent"
          >
            <svg
              width={18}
              height={18}
              viewBox="0 0 512 512"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
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
          </button>
        </div>

        <StateDrawerFilterMenu
          id={filterTrayId}
          open={filtersOpen}
          selected={evalFilters}
          onChange={onEvalFiltersChange}
          onClose={() => onFiltersOpenChange(false)}
        />
      </div>

      {searchOpen ? (
        <div className="mt-4 flex justify-end">
          <div className="w-full max-w-drawer-content [&>div]:!mt-0">
            <StateDrawerSearch
              id={searchId}
              value={searchQuery}
              onChange={onSearchChange}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
