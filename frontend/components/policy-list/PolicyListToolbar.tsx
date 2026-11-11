"use client";

import { useId } from "react";

import {
  StateDrawerFilterButton,
  StateDrawerFilterMenu,
} from "@/components/state/StateDrawerFilter";
import { StateDrawerToolbarSearch } from "@/components/state/StateDrawerSearch";
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

          <StateDrawerToolbarSearch
            id={searchId}
            open={searchOpen}
            onOpenChange={onSearchOpenChange}
            value={searchQuery}
            onChange={onSearchChange}
          />
        </div>

        <StateDrawerFilterMenu
          id={filterTrayId}
          open={filtersOpen}
          selected={evalFilters}
          onChange={onEvalFiltersChange}
          onClose={() => onFiltersOpenChange(false)}
        />
      </div>
    </div>
  );
}
