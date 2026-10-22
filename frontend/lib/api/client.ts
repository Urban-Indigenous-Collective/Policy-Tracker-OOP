import type {
  PublicApiHealthResponse,
  PublicBillDetailResponse,
  PublicStateBillsResponse,
  PublicStatesResponse,
} from "@/lib/api/types";

/** Browser: same-origin `/api` (Next rewrite in dev, nginx in prod). */
export function getBrowserApiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE ?? "";
}

/** Server Components / generateMetadata — rewrites do not apply to Node fetch. */
export function getServerApiBase(): string {
  return (
    process.env.INTERNAL_API_BASE ??
    process.env.FLASK_DEV_URL ??
    "http://127.0.0.1:5000"
  );
}

function resolveApiBase(explicit?: "browser" | "server"): string {
  if (explicit === "server") return getServerApiBase();
  if (explicit === "browser") return getBrowserApiBase();
  return typeof window === "undefined" ? getServerApiBase() : getBrowserApiBase();
}

function apiUrl(path: string, base?: "browser" | "server"): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const root = resolveApiBase(base);
  return `${root}${normalized}`;
}

export async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

const defaultFetchInit: RequestInit = {
  headers: { Accept: "application/json" },
};

export async function fetchPublicStates(
  options?: { base?: "browser" | "server" },
): Promise<PublicStatesResponse> {
  const res = await fetch(apiUrl("/api/v1/states", options?.base), {
    ...defaultFetchInit,
    next: options?.base === "server" ? { revalidate: 300 } : undefined,
  });
  return parseJson(res);
}

export async function fetchPublicApiHealth(
  options?: { base?: "browser" | "server" },
): Promise<PublicApiHealthResponse> {
  const res = await fetch(apiUrl("/api/v1/health", options?.base), defaultFetchInit);
  return parseJson(res);
}

export async function fetchStateBills(
  code: string,
  options?: { base?: "browser" | "server" },
): Promise<PublicStateBillsResponse> {
  const encoded = encodeURIComponent(code);
  const res = await fetch(apiUrl(`/api/v1/states/${encoded}/bills`, options?.base), {
    ...defaultFetchInit,
    next: options?.base === "server" ? { revalidate: 300 } : undefined,
  });
  return parseJson(res);
}

export async function fetchBillById(
  recordId: string,
  options?: { base?: "browser" | "server" },
): Promise<PublicBillDetailResponse> {
  const encoded = encodeURIComponent(recordId);
  const res = await fetch(apiUrl(`/api/v1/bills/${encoded}`, options?.base), {
    ...defaultFetchInit,
    next: options?.base === "server" ? { revalidate: 300 } : undefined,
  });
  return parseJson(res);
}
