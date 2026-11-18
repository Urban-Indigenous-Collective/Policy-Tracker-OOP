"use client";

import { useEffect, useRef } from "react";

import { trackBillOpen, trackStateOpen } from "@/lib/analytics/events";
import { consumeSelectionSource } from "@/lib/analytics/selection-source";

type MapSelectionAnalyticsProps = {
  selectedState: string | null;
  selectedBillSlug: string | null;
};

/**
 * Fires state_open / bill_open when map selection changes.
 * Source comes from {@link setNextSelectionSource} (map/drawer/embed) or
 * defaults to `url` for deep links and browser history.
 */
export function MapSelectionAnalytics({
  selectedState,
  selectedBillSlug,
}: MapSelectionAnalyticsProps) {
  const prevState = useRef<string | null>(null);
  const prevBillKey = useRef<string | null>(null);

  useEffect(() => {
    if (!selectedState) {
      prevState.current = null;
      return;
    }
    if (selectedState === prevState.current) return;
    prevState.current = selectedState;
    trackStateOpen({
      stateCode: selectedState,
      source: consumeSelectionSource(),
    });
  }, [selectedState]);

  useEffect(() => {
    if (!selectedState || !selectedBillSlug) {
      prevBillKey.current = null;
      return;
    }
    const key = `${selectedState}:${selectedBillSlug}`;
    if (key === prevBillKey.current) return;
    prevBillKey.current = key;
    trackBillOpen({
      stateCode: selectedState,
      billSlug: selectedBillSlug,
      source: consumeSelectionSource(),
    });
  }, [selectedState, selectedBillSlug]);

  return null;
}
