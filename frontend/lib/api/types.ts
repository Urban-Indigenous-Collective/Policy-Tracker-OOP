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

export type PublicMapLayerStateEntry = {
  code: string;
  name: string;
  category: LegendCategory;
  billCount: number;
};

export type PublicMapLayers = {
  stateLegislation: { states: Record<string, PublicMapLayerStateEntry> };
  nationalLegislation: { category: LegendCategory | null };
  dojInitiative: {
    states: Record<string, PublicMapLayerStateEntry>;
    category: LegendCategory | null;
  };
};

export type PublicStatesResponse = {
  summary: MapSummary;
  states: Record<string, StateMapEntry>;
  mapLayers?: PublicMapLayers;
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
  optionalLink?: string;
  billTextUrl?: string;
  categories: string[];
  /** Main v3 eval selects. Drawer filters treat `"Yes"` and `"Somewhat"` as a match. */
  mechanismsForEvaluation?: string;
  genderInclusiveLanguage?: string;
  preventionEfforts?: string;
  survivorRelativeInput?: string;
  centeringIndigenousVoices?: string;
  /** True when Main v3 Indigenous Sponsorship text is present. */
  hasIndigenousSponsorship?: boolean;
  uicPros?: string;
  uicCons?: string;
  reviewStatus?: string;
  /** Main v3 multiline explanations (bill detail only). */
  mechanismsForEvaluationJustification?: string;
  genderInclusiveLanguageJustification?: string;
  preventionEffortsJustification?: string;
  survivorRelativeInputJustification?: string;
  centeringIndigenousVoicesJustification?: string;
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
  /** Live bills with Main v3 Indigenous Sponsorship populated. */
  indigenousSponsorshipCount?: number;
  cacheAgeSeconds: number;
  generatedAt: string;
};

export type PublicSitemapResponse = {
  paths: string[];
  billCount: number;
  liveCount: number;
  skippedNoSlug: number;
  skippedNotIndexable: number;
  generatedAt: string;
  cacheAgeSeconds: number;
};

export type PublicBillDetailResponse = {
  bill: PublicBill;
  generatedAt: string;
  cacheAgeSeconds: number;
};
