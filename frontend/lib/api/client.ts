import type { PublicApiHealthResponse, PublicStatesResponse } from "@/lib/api/types";

const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "";

function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${apiBase}${normalized}`;
}

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchPublicStates(): Promise<PublicStatesResponse> {
  const res = await fetch(apiUrl("/api/v1/states"), {
    headers: { Accept: "application/json" },
  });
  return parseJson(res);
}

export async function fetchPublicApiHealth(): Promise<PublicApiHealthResponse> {
  const res = await fetch(apiUrl("/api/v1/health"), {
    headers: { Accept: "application/json" },
  });
  return parseJson(res);
}
