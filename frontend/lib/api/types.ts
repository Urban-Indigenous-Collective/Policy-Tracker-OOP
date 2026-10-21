/** Mirrors docs/API_V1.md — public Flask /api/v1 responses. */

export type LegendCategory =
  | "passed"
  | "passedAdditional"
  | "pending"
  | "failed"
  | "failedAdditional";

export type MapSummary = {
  passed: number;
  pending: number;
  rejected: number;
};

export type StateMapEntry = {
  code: string;
  name: string;
  category: LegendCategory;
  billCount: number;
};

export type PublicStatesResponse = {
  summary: MapSummary;
  states: Record<string, StateMapEntry>;
  generatedAt: string;
  cacheAgeSeconds: number;
};

export type PublicBill = {
  id: string;
  slug: string;
  name: string;
  state: string;
  status: string;
  progression: string;
  billNumber: string;
  session: string;
  lastUpdate: string;
  summary: string;
  billOverviewUrl: string;
  categories: string[];
  uicPros?: string;
  uicCons?: string;
  reviewStatus?: string;
};

export type PublicStateBillsResponse = {
  state: string;
  bills: PublicBill[];
  generatedAt: string;
  cacheAgeSeconds: number;
};

export type PublicApiHealthResponse = {
  ok: boolean;
  liveCount: number;
  cacheAgeSeconds: number;
  generatedAt: string;
};
