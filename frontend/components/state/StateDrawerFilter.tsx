"use client";

import { useEffect } from "react";

import {
  DRAWER_EVAL_FILTERS,
  type DrawerEvalFilterKey,
} from "@/lib/state/drawer-eval-filters";

type StateDrawerFilterButtonProps = {
  open: boolean;
  active: boolean;
  controlsId: string;
  onToggle: () => void;
};

export function StateDrawerFilterButton({
  open,
  active,
  controlsId,
  onToggle,
}: StateDrawerFilterButtonProps) {
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={controlsId}
      onClick={onToggle}
      className={`uic-drawer-filter-pill absolute top-0 left-drawer-filter-from-content h-drawer-filter-pill w-drawer-filter-pill cursor-pointer rounded-drawer-filter border bg-transparent font-sans text-drawer-filter font-semibold uppercase outline-none focus-visible:ring-2 focus-visible:ring-accent ${
        active || open
          ? "border-accent text-accent"
          : "border-foreground text-foreground"
      }`}
    >
      Filter
    </button>
  );
}

type StateDrawerFilterMenuProps = {
  id: string;
  open: boolean;
  selected: readonly DrawerEvalFilterKey[];
  onChange: (next: DrawerEvalFilterKey[]) => void;
  onClose: () => void;
};

/** Dropdown under the policies row, kept inside the content gutters. */
export function StateDrawerFilterMenu({
  id,
  open,
  selected,
  onChange,
  onClose,
}: StateDrawerFilterMenuProps) {
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const menu = document.getElementById(id);
      const root = menu?.parentElement;
      if (root && !root.contains(event.target as Node)) onClose();
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [id, onClose, open]);

  const toggleKey = (key: DrawerEvalFilterKey) => {
    onChange(
      selected.includes(key)
        ? selected.filter((item) => item !== key)
        : [...selected, key],
    );
  };

  if (!open) return null;

  return (
    <div
      id={id}
      role="group"
      aria-label="Policy analysis filters"
      className="absolute top-full right-0 left-0 z-20 mt-drawer-filter-menu flex flex-wrap gap-drawer-filter-stack rounded-drawer-filter border border-surface-border bg-background p-drawer-filter-options-x"
    >
      {DRAWER_EVAL_FILTERS.map((option) => {
        const checked = selected.includes(option.key);
        return (
          <button
            key={option.key}
            type="button"
            aria-pressed={checked}
            onClick={() => toggleKey(option.key)}
            className={`uic-drawer-filter-option w-auto cursor-pointer rounded-drawer-filter border bg-transparent px-drawer-filter-option-x py-drawer-filter-option-y font-sans text-drawer-filter font-semibold uppercase outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              checked
                ? "border-accent text-accent"
                : "border-foreground text-foreground"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
