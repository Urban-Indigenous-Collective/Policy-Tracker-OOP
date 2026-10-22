const YEAR_OR_SPAN = String.raw`\d{4}(?:\s*[-–]\s*\d{4})?`;

/** Year or year span only. Omits the line when the session has no year. */
export function formatDrawerSessionYear(session: string | null | undefined): string {
  const trimmed = session?.trim() ?? "";
  if (!trimmed) return "";

  const leading = trimmed.match(new RegExp(`^(${YEAR_OR_SPAN})`));
  if (leading?.[1]) return leading[1].replace(/\s*([-–])\s*/, "$1");

  const stripped = trimmed.replace(/\s*(?:(?:regular|special)\s+)?session$/i, "").trim();
  const exact = stripped.match(new RegExp(`^(${YEAR_OR_SPAN})$`));
  return exact?.[1] ? exact[1].replace(/\s*([-–])\s*/, "$1") : "";
}
