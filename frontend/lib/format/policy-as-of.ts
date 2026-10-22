const POLICY_AS_OF_TZ = "America/New_York";

/** Long US date for intro footnote (matches legacy Figma copy style). */
export function formatPolicyAsOfDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat("en-US", {
    timeZone: POLICY_AS_OF_TZ,
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(date);
}
