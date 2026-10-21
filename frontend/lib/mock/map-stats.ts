import type { LegendCategory } from "@/lib/map/legend";

export const MAP_SUMMARY_STATS = {
  passed: 153,
  pending: 63,
  rejected: 23,
} as const;

/** Demo state colors for static shell (Phase 2 replaces with API). */
export const MOCK_STATE_CATEGORIES: Partial<Record<string, LegendCategory>> = {
  WA: "passed",
  OR: "passed",
  CA: "passedAdditional",
  MN: "passed",
  MT: "passed",
  ND: "pending",
  UT: "pending",
  AZ: "pending",
  TX: "failed",
  FL: "failed",
  NY: "failed",
};
