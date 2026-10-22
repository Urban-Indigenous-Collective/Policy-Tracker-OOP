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
  liveCount?: number;
  mainV3Count?: number;
  /** Last successful nightly status refresh (ISO), when available. */
  policyDataAsOf?: string | null;
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
  chamber?: string;
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
  mainV3Count?: number;
  cacheAgeSeconds: number;
  generatedAt: string;
};

export type PublicBillDetailResponse = {
  bill: PublicBill;
  generatedAt: string;
  cacheAgeSeconds: number;
};
