export const publicApiKeys = {
  all: ["public"] as const,
  states: () => [...publicApiKeys.all, "states"] as const,
  stateBills: (code: string) =>
    [...publicApiKeys.all, "state", code.toUpperCase(), "bills"] as const,
  bill: (id: string) => [...publicApiKeys.all, "bill", id] as const,
};

export const PUBLIC_QUERY_STALE_MS = 300_000;
