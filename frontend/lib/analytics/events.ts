import { trackEvent } from "@/lib/analytics/track";

/** How the user reached a state or bill surface. */
export type SelectionSource =
  | "map"
  | "drawer"
  | "policy_list"
  | "embed"
  | "url";

export type SubscribeSource = "state_drawer" | "policy_list";

export type OutboundLinkType =
  | "bill_text"
  | "optional_link"
  | "bill_overview";

export type CtaId =
  | "donate"
  | "nav_policy_map"
  | "nav_policy_list"
  | "footer_connect"
  | "footer_about"
  | "footer_social"
  | "footer_learn_more"
  | "embed_dashboard";

export type SearchContext = "state_drawer" | "policy_list" | "bill_panel";

export type FilterContext = "state_drawer" | "policy_list";

export function trackStateOpen(args: {
  stateCode: string;
  source: SelectionSource;
}): void {
  trackEvent(
    "state_open",
    { state_code: args.stateCode, source: args.source },
    { dedupeKey: `state_open:${args.stateCode}:${args.source}` },
  );
}

export function trackBillOpen(args: {
  stateCode: string;
  billSlug: string;
  source: SelectionSource;
}): void {
  trackEvent(
    "bill_open",
    {
      state_code: args.stateCode,
      bill_slug: args.billSlug,
      source: args.source,
    },
    {
      dedupeKey: `bill_open:${args.stateCode}:${args.billSlug}:${args.source}`,
    },
  );
}

export function trackSubscribeOpen(args: {
  stateCode: string;
  source: SubscribeSource;
}): void {
  trackEvent(
    "subscribe_open",
    {
      state_code: args.stateCode,
      source: args.source,
    },
    { dedupeKey: `subscribe_open:${args.stateCode}:${args.source}` },
  );
}

export function trackSubscribeEmailSubmit(args: { stateCode: string }): void {
  trackEvent("subscribe_email_submit", { state_code: args.stateCode });
}

export function trackSubscribeSuccess(args: {
  stateCode: string;
  newlyAdded: boolean;
}): void {
  trackEvent("subscribe_success", {
    state_code: args.stateCode,
    newly_added: args.newlyAdded,
  });
}

export function trackSubscribeOtpSubmit(args: { stateCode: string }): void {
  trackEvent("subscribe_otp_submit", { state_code: args.stateCode });
}

export function trackSubscribeOtpSuccess(args: { stateCode: string }): void {
  trackEvent("subscribe_otp_success", { state_code: args.stateCode });
}

export function trackSubscribeAbandon(args: {
  stateCode: string;
  step: string;
}): void {
  trackEvent("subscribe_abandon", {
    state_code: args.stateCode,
    step: args.step,
  });
}

export function trackDigestStart(): void {
  trackEvent("digest_start", {}, { dedupeKey: "digest_start" });
}

export function trackDigestSubmit(): void {
  trackEvent("digest_submit");
}

export function trackDigestSuccess(): void {
  trackEvent("digest_success");
}

export function trackDigestError(): void {
  trackEvent("digest_error");
}

export function trackOutboundClick(args: {
  linkType: OutboundLinkType;
  stateCode: string;
  billSlug: string;
  url: string;
}): void {
  trackEvent(
    "outbound_click",
    {
      link_type: args.linkType,
      state_code: args.stateCode,
      bill_slug: args.billSlug,
      link_url: args.url,
    },
    { beacon: true },
  );
}

export function trackCtaClick(args: {
  ctaId: CtaId;
  label?: string;
  url?: string;
}): void {
  trackEvent(
    "cta_click",
    {
      cta_id: args.ctaId,
      cta_label: args.label,
      link_url: args.url,
    },
    // Donate / footer / embed leave the page before xhr can finish.
    { beacon: true },
  );
}

export function trackMapLayerToggle(args: {
  layer: string;
  active: boolean;
}): void {
  trackEvent("map_layer_toggle", {
    layer: args.layer,
    active: args.active,
  });
}

export function trackSearchSubmit(args: {
  context: SearchContext;
  queryLength: number;
  stateCode?: string;
}): void {
  trackEvent("search_submit", {
    search_context: args.context,
    query_length: args.queryLength,
    state_code: args.stateCode,
  });
}

export function trackFilterChange(args: {
  context: FilterContext;
  filterType: "eval" | "topic";
  filters: string[];
  stateCode?: string;
}): void {
  trackEvent("filter_change", {
    filter_context: args.context,
    filter_type: args.filterType,
    filters: args.filters.join(","),
    filter_count: args.filters.length,
    state_code: args.stateCode,
  });
}

export function trackBillEngage(args: {
  stateCode: string;
  billSlug: string;
  dwellMs: number;
  scrolledAnalysis: boolean;
}): void {
  trackEvent("bill_engage", {
    state_code: args.stateCode,
    bill_slug: args.billSlug,
    dwell_ms: args.dwellMs,
    scrolled_analysis: args.scrolledAnalysis,
  });
}

export function trackPolicyListExpand(args: {
  stateCode: string;
  hiddenCount: number;
}): void {
  trackEvent("policy_list_expand", {
    state_code: args.stateCode,
    hidden_count: args.hiddenCount,
  });
}

export function trackManageView(args: {
  status: string;
  stateCount: number;
}): void {
  trackEvent(
    "manage_view",
    {
      manage_status: args.status,
      state_count: args.stateCount,
    },
    { dedupeKey: `manage_view:${args.status}` },
  );
}

export function trackManageUnsubscribe(args: {
  target: string;
  remainingCount: number;
}): void {
  trackEvent("manage_unsubscribe", {
    unsubscribe_target: args.target,
    remaining_count: args.remainingCount,
  });
}
