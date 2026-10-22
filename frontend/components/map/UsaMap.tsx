"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { LegendCategory } from "@/lib/map/legend";
import { ensureMapLegendPatterns } from "@/lib/map/map-legend-patterns";
import { applyMapPaintStyles } from "@/lib/map/map-paint";
import { STATE_NAMES, svgIdToStateCode } from "@/lib/map/state-codes";

type UsaMapProps = {
  stateCategories: Record<string, LegendCategory>;
  selectedState?: string | null;
  onStateSelect?: (stateCode: string) => void;
};

function prepareStateRegion(node: Element, code: string) {
  const name = STATE_NAMES[code] ?? code;
  node.setAttribute("role", "button");
  node.setAttribute("tabindex", "0");
  node.setAttribute("data-state-code", code);
  node.classList.add("cursor-pointer", "focus:outline-none");
}

function syncRegionA11y(container: HTMLElement, selected: string | null) {
  container.querySelectorAll("[data-state-code]").forEach((node) => {
    const code = node.getAttribute("data-state-code");
    if (!code) return;
    const name = STATE_NAMES[code] ?? code;
    node.setAttribute("aria-pressed", selected === code ? "true" : "false");
    node.setAttribute(
      "aria-label",
      `${name}. ${selected === code ? "Selected." : "Select to view policies."}`,
    );
  });
}

export function UsaMap({
  stateCategories,
  selectedState = null,
  onStateSelect,
}: UsaMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [svgReady, setSvgReady] = useState(false);
  const onSelectRef = useRef(onStateSelect);

  useEffect(() => {
    onSelectRef.current = onStateSelect;
  }, [onStateSelect]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let detachListeners: (() => void) | undefined;
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
        ensureMapLegendPatterns(svg);

        const onSvgClick = (event: Event) => {
          const target = event.target;
          if (!(target instanceof Element)) return;
          const region = target.closest("[data-state-code]");
          if (!region || !container.contains(region)) return;
          const code = region.getAttribute("data-state-code");
          if (code) onSelectRef.current?.(code);
        };

        const onSvgKeyDown = (event: Event) => {
          if (!(event instanceof KeyboardEvent)) return;
          if (event.key !== "Enter" && event.key !== " ") return;
          const target = event.target;
          if (!(target instanceof Element)) return;
          const region = target.closest("[data-state-code]");
          if (!region) return;
          event.preventDefault();
          const code = region.getAttribute("data-state-code");
          if (code) onSelectRef.current?.(code);
        };

        svg.addEventListener("click", onSvgClick);
        svg.addEventListener("keydown", onSvgKeyDown);

        svg.querySelectorAll("[id^='US-']").forEach((node) => {
          const code = svgIdToStateCode(node.id);
          if (!code) return;
          prepareStateRegion(node, code);
        });

        container.replaceChildren(svg);
        detachListeners = () => {
          svg.removeEventListener("click", onSvgClick);
          svg.removeEventListener("keydown", onSvgKeyDown);
        };
        if (!cancelled) setSvgReady(true);
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
      detachListeners?.();
    };
  }, []);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container || !svgReady) return;
    applyMapPaintStyles(container, stateCategories, selectedState ?? null);
    syncRegionA11y(container, selectedState ?? null);
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
