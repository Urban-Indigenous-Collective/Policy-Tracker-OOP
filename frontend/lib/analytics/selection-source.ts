import type { SelectionSource } from "@/lib/analytics/events";

/**
 * Next interaction source for map URL/local selection changes.
 * Click handlers set this before updating selection; deep links / back-forward
 * leave the default `"url"`.
 */
let nextSource: SelectionSource = "url";

export function setNextSelectionSource(source: SelectionSource): void {
  nextSource = source;
}

export function consumeSelectionSource(): SelectionSource {
  const source = nextSource;
  nextSource = "url";
  return source;
}
