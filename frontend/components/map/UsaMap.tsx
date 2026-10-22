"use client";

import { useEffect, useRef, useState } from "react";
import type { LegendCategory } from "@/lib/map/legend";
import { applyMapPaintStyles } from "@/lib/map/map-paint";
import { STATE_NAMES, svgIdToStateCode } from "@/lib/map/state-codes";

type UsaMapProps = {
  stateCategories: Record<string, LegendCategory>;
  selectedState?: string | null;
  onStateSelect?: (stateCode: string | null) => void;
};

function prepareStateRegion(node: Element, code: string) {
  const name = STATE_NAMES[code] ?? code;
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
}

export function UsaMap({
  stateCategories,
  selectedState = null,
  onStateSelect,
}: UsaMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [svgReady, setSvgReady] = useState(false);
  const selectedRef = useRef(selectedState);
  const onSelectRef = useRef(onStateSelect);
  const categoriesRef = useRef(stateCategories);

  useEffect(() => {
    selectedRef.current = selectedState;
    onSelectRef.current = onStateSelect;
    categoriesRef.current = stateCategories;
  }, [onStateSelect, selectedState, stateCategories]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    setSvgReady(false);
    setLoadError(null);

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
        if (!(svg instanceof SVGSVGElement)) {
          throw new Error("Invalid SVG root");
        }
        if (svg.querySelector("parsererror")) {
          throw new Error("Invalid SVG");
        }

        svg.setAttribute("role", "group");
        svg.setAttribute("aria-label", "United States policy map");
        svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
        svg.removeAttribute("overflow");
        svg.classList.add("h-auto", "w-full", "max-w-full");

        svg.querySelectorAll("[id^='US-']").forEach((node) => {
          const code = svgIdToStateCode(node.id);
          if (!code) return;

          prepareStateRegion(node, code);

          const activate = () => {
            const current = selectedRef.current;
            const next = current === code ? null : code;
            onSelectRef.current?.(next);
          };

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
        applyMapPaintStyles(
          container,
          categoriesRef.current,
          selectedRef.current ?? null,
        );
        setSvgReady(true);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Load failed";
          setLoadError(message);
          setSvgReady(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !svgReady) return;
    applyMapPaintStyles(container, stateCategories, selectedState ?? null);
  }, [selectedState, stateCategories, svgReady]);

  if (loadError) {
    return (
      <p className="text-sm text-red-400" role="alert">
        Could not load map ({loadError}).
      </p>
    );
  }

  return (
    <div className="relative w-full">
      {!svgReady ? (
        <div
          className="min-h-map w-full animate-pulse rounded bg-white/[0.04] sm:min-h-map-sm"
          aria-label="Loading United States policy map"
          role="status"
        />
      ) : null}
      <div
        ref={containerRef}
        className={
          svgReady
            ? "min-h-map w-full sm:min-h-map-sm [&_svg]:pointer-events-auto"
            : "absolute h-0 w-0 overflow-hidden"
        }
        aria-hidden={!svgReady}
      />
    </div>
  );
}
