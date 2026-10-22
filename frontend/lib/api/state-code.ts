/** Federal jurisdiction key — matches `discovery/federal_schema.FEDERAL_STATE`. */
export const NATIONAL_STATE_CODE = "National";

/** Uppercase 2-letter codes for URLs; mirrors public_api/states.py for US SVG states. */
export function normalizeStateRouteParam(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.toLowerCase() === "national") {
    return NATIONAL_STATE_CODE;
  }
  return trimmed.toUpperCase();
}

export function isSvgMapStateCode(code: string): boolean {
  return /^[A-Z]{2}$/.test(code) && code !== "US";
}

/** Map drawer + `/states/[code]` routes (SVG states and federal National). */
export function isPublicStatePanelCode(code: string): boolean {
  return isSvgMapStateCode(code) || code === NATIONAL_STATE_CODE;
}

/** Path segment for `router.replace('/states/…')`. */
export function stateCodeForUrl(code: string): string {
  return code === NATIONAL_STATE_CODE ? NATIONAL_STATE_CODE : code.toUpperCase();
}
