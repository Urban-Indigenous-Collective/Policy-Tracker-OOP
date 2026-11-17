"use client";

import { useEffect } from "react";

import type { LegendCategory } from "@/lib/map/legend";
import {
  stateCategoryFilterActiveClass,
  stateCategoryFilterFocusRingClass,
} from "@/lib/map/state-category-title-class";
import {
  DRAWER_FILTERS,
  type DrawerFilterKey,
} from "@/lib/state/drawer-eval-filters";
import {
  DRAWER_TOPIC_FILTERS,
  type DrawerTopicFilterKey,
} from "@/lib/state/drawer-topic-filters";

type StateDrawerFilterButtonProps = {
  open: boolean;
  active: boolean;
  controlsId: string;
  stateCategory?: LegendCategory;
  onToggle: () => void;
  /** Drawer: aligned to policies row; toolbar: inline in policy list controls. */
  placement?: "drawer" | "toolbar";
};

export function StateDrawerFilterButton({
  open,
  active,
  controlsId,
  stateCategory,
  onToggle,
  placement = "drawer",
}: StateDrawerFilterButtonProps) {
  const emphasis = active || open;
  const activeClass = stateCategoryFilterActiveClass(stateCategory);
  const focusRingClass = stateCategoryFilterFocusRingClass(stateCategory);
  const placementClass =
    placement === "drawer"
      ? "absolute top-0 left-drawer-filter-from-content"
      : "shrink-0";

  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={controlsId}
      onClick={onToggle}
      className={`uic-drawer-filter-pill ${placementClass} box-border h-drawer-filter-pill w-drawer-filter-pill cursor-pointer rounded-drawer-filter border bg-transparent text-drawer-filter outline-none focus-visible:ring-2 ${focusRingClass} ${
        emphasis
          ? activeClass
          : "border-foreground text-foreground"
      }`}
    >
      <span className="uic-drawer-filter-pill-label">Filter</span>
    </button>
  );
}

type FilterChipProps = {
  label: string;
  checked: boolean;
  activeClass: string;
  focusRingClass: string;
  onToggle: () => void;
};

function FilterChip({
  label,
  checked,
  activeClass,
  focusRingClass,
  onToggle,
}: FilterChipProps) {
  return (
    <button
      type="button"
      aria-pressed={checked}
      onClick={onToggle}
      className={`uic-drawer-filter-option w-auto cursor-pointer rounded-drawer-filter border bg-transparent px-drawer-filter-option-x py-drawer-filter-option-y font-sans text-drawer-filter font-semibold uppercase outline-none focus-visible:ring-2 ${focusRingClass} ${
        checked
          ? activeClass
          : "border-foreground text-foreground"
      }`}
    >
      {label}
    </button>
  );
}

type StateDrawerFilterMenuProps = {
  id: string;
  open: boolean;
  selected: readonly DrawerFilterKey[];
  selectedTopics: readonly DrawerTopicFilterKey[];
  stateCategory?: LegendCategory;
  onChange: (next: DrawerFilterKey[]) => void;
  onTopicsChange: (next: DrawerTopicFilterKey[]) => void;
  onClose: () => void;
};

/** Dropdown under the policies row, kept inside the content gutters. */
export function StateDrawerFilterMenu({
  id,
  open,
  selected,
  selectedTopics,
  stateCategory,
  onChange,
  onTopicsChange,
  onClose,
}: StateDrawerFilterMenuProps) {
  const activeClass = stateCategoryFilterActiveClass(stateCategory);
  const focusRingClass = stateCategoryFilterFocusRingClass(stateCategory);
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      const menu = document.getElementById(id);
      if (!menu) return;
      if (menu.contains(target)) return;
      const trigger = document.querySelector(`[aria-controls="${CSS.escape(id)}"]`);
      if (trigger?.contains(target)) return;
      onClose();
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [id, onClose, open]);

  const toggleKey = (key: DrawerFilterKey) => {
    onChange(
      selected.includes(key)
        ? selected.filter((item) => item !== key)
        : [...selected, key],
    );
  };

  const toggleTopic = (key: DrawerTopicFilterKey) => {
    onTopicsChange(
      selectedTopics.includes(key)
        ? selectedTopics.filter((item) => item !== key)
        : [...selectedTopics, key],
    );
  };

  if (!open) return null;

  return (
    <div
      id={id}
      role="group"
      aria-label="Policy filters"
      className="absolute top-full right-0 left-0 z-20 mt-drawer-filter-menu flex flex-col gap-drawer-filter-menu rounded-drawer-filter border border-surface-border bg-background p-drawer-filter-options-x py-drawer-filter-option-y"
    >
      <div role="group" aria-label="Topic filters">
        <p className="uic-drawer-filter-pill-label mb-drawer-filter-stack text-muted">
          Topic
        </p>
        <div className="flex flex-wrap gap-drawer-filter-stack">
          {DRAWER_TOPIC_FILTERS.map((option) => (
            <FilterChip
              key={option.key}
              label={option.label}
              checked={selectedTopics.includes(option.key)}
              activeClass={activeClass}
              focusRingClass={focusRingClass}
              onToggle={() => toggleTopic(option.key)}
            />
          ))}
        </div>
      </div>

      <div role="group" aria-label="Analysis filters">
        <p className="uic-drawer-filter-pill-label mb-drawer-filter-stack text-muted">
          Analysis
        </p>
        <div className="flex flex-wrap gap-drawer-filter-stack">
          {DRAWER_FILTERS.map((option) => (
            <FilterChip
              key={option.key}
              label={option.label}
              checked={selected.includes(option.key)}
              activeClass={activeClass}
              focusRingClass={focusRingClass}
              onToggle={() => toggleKey(option.key)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
