import {
  MAP_PENDING_PATTERN_ID,
  policyStatusColor,
} from "@/lib/design/tokens";

const SVG_NS = "http://www.w3.org/2000/svg";

/** Diagonal stripe fill matching `public/ui/legend-pending.svg`. */
export function ensureMapLegendPatterns(svg: SVGSVGElement): void {
  let defs = svg.querySelector("defs");
  if (!defs) {
    defs = document.createElementNS(SVG_NS, "defs");
    svg.prepend(defs);
  }
  if (defs.querySelector(`#${MAP_PENDING_PATTERN_ID}`)) {
    return;
  }

  const pattern = document.createElementNS(SVG_NS, "pattern");
  pattern.setAttribute("id", MAP_PENDING_PATTERN_ID);
  pattern.setAttribute("patternUnits", "userSpaceOnUse");
  pattern.setAttribute("width", "10");
  pattern.setAttribute("height", "10");
  pattern.setAttribute("patternTransform", "rotate(45)");

  const base = document.createElementNS(SVG_NS, "rect");
  base.setAttribute("width", "10");
  base.setAttribute("height", "10");
  base.setAttribute("fill", policyStatusColor.pendingBase);

  const stripe = document.createElementNS(SVG_NS, "line");
  stripe.setAttribute("x1", "0");
  stripe.setAttribute("y1", "0");
  stripe.setAttribute("x2", "0");
  stripe.setAttribute("y2", "10");
  stripe.setAttribute("stroke", policyStatusColor.pendingStripe);
  stripe.setAttribute("stroke-width", "3");

  pattern.append(base, stripe);
  defs.append(pattern);
}
