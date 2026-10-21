"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { mapInteraction } from "@/lib/design/tokens";
import { LEGEND_FILL, type LegendCategory } from "@/lib/map/legend";
import { STATE_NAMES, svgIdToStateCode } from "@/lib/map/state-codes";
import { MOCK_STATE_CATEGORIES } from "@/lib/mock/map-stats";

type UsaMapProps = {
  onStateSelect?: (stateCode: string) => void;
};

function fillForState(code: string): string {
  const category: LegendCategory =
    MOCK_STATE_CATEGORIES[code] ?? "failed";
  return LEGEND_FILL[category];
}

function applyRegionPaint(
  node: Element,
  fill: string,
  opacity: string,
) {
  const paint = (el: Element) => {
    if (el instanceof SVGGraphicsElement) {
      el.setAttribute("fill", fill);
      el.setAttribute("stroke", mapInteraction.stroke);
      el.setAttribute("stroke-width", mapInteraction.strokeWidth);
      el.setAttribute("opacity", opacity);
    }
  };
  paint(node);
  node.querySelectorAll("path").forEach(paint);
}

export function UsaMap({ onStateSelect }: UsaMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const handleSelect = useCallback(
    (code: string) => {
      setSelected((prev) => {
        const next = prev === code ? null : code;
        if (next) onStateSelect?.(next);
        return next;
      });
    },
    [onStateSelect],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;

    fetch("/maps/usa.svg")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((svgText) => {
        if (cancelled || !container) return;

        const parser = new DOMParser();
        const doc = parser.parseFromString(svgText, "image/svg+xml");
        const svg = doc.documentElement;
        if (svg.querySelector("parsererror")) {
          throw new Error("Invalid SVG");
        }

        svg.setAttribute("role", "group");
        svg.setAttribute("aria-label", "United States policy map");
        svg.classList.add("h-auto", "w-full", "max-w-full");

        const regionIds = new Set<string>();
        svg.querySelectorAll("[id^='US-']").forEach((node) => {
          if (node.id) regionIds.add(node.id);
        });

        regionIds.forEach((id) => {
          const code = svgIdToStateCode(id);
          if (!code) return;

          const node = svg.querySelector(`#${CSS.escape(id)}`);
          if (!node) return;

          const name = STATE_NAMES[code] ?? code;
          const fill = fillForState(code);
          applyRegionPaint(node, fill, "1");

          node.setAttribute("role", "button");
          node.setAttribute("tabindex", "0");
          node.setAttribute("data-state-code", code);
          node.setAttribute("aria-label", `${name}. Select to view policies.`);
          node.classList.add(
            "cursor-pointer",
            "transition-opacity",
            "duration-200",
            "focus:outline-none",
          );

          const activate = () => handleSelect(code);

          node.addEventListener("click", activate);
          node.addEventListener("keydown", (event: Event) => {
            if (!(event instanceof KeyboardEvent)) return;
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              activate();
            }
          });
        });

        container.replaceChildren(svg);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Load failed";
          setLoadError(message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [handleSelect]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.querySelectorAll("[id^='US-']").forEach((node) => {
      const code = svgIdToStateCode(node.id);
      if (!code) return;

      const fill = fillForState(code);
      const opacity =
        selected && code === selected
          ? mapInteraction.selectedOpacity
          : "1";
      applyRegionPaint(node, fill, opacity);
    });
  }, [selected]);

  if (loadError) {
    return (
      <p className="text-sm text-red-400" role="alert">
        Could not load map ({loadError}).
      </p>
    );
  }

  return (
    <div className="relative w-full">
      <div ref={containerRef} className="min-h-map w-full sm:min-h-map-sm" />
      {selected ? (
        <p className="mt-3 font-mono text-sm text-accent" aria-live="polite">
          Selected: {STATE_NAMES[selected] ?? selected} ({selected}) — click
          again to clear
        </p>
      ) : null}
    </div>
  );
}
