/** Uppercase 2-letter codes for URLs; mirrors public_api/states.py for US SVG states. */
export function normalizeStateRouteParam(raw: string): string {
  return raw.trim().toUpperCase();
}

export function isSvgMapStateCode(code: string): boolean {
  return /^[A-Z]{2}$/.test(code) && code !== "US";
}
