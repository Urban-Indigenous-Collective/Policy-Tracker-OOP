import { getBrowserApiBase } from "@/lib/api/client";

function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${getBrowserApiBase()}${normalized}`;
}

export type SubscribeSignupResponse = {
  ok: boolean;
  status: "subscribed" | "verification_required";
  email: string;
  state: string;
  states?: string[];
  added?: string | false;
  alreadySubscribed?: boolean;
  /** True when this email already had subscriptions before this signup. */
  hasExistingSubscriptions: boolean;
  message: string;
};

export type SubscribeVerifyResponse = {
  ok: boolean;
  sessionToken: string;
  email: string;
  states: string[];
};

export type SubscribeStatesResponse = {
  ok?: boolean;
  email: string;
  states: string[];
  added?: string;
  removed?: string;
};

type ApiErrorBody = {
  error?: string;
  message?: string;
};

async function parseSubscribeJson<T>(res: Response): Promise<T> {
  const body = (await res.json().catch(() => null)) as (T & ApiErrorBody) | null;
  if (!res.ok) {
    const message =
      body && typeof body === "object" && "message" in body && body.message
        ? String(body.message)
        : `HTTP ${res.status}`;
    const err = new Error(message) as Error & { code?: string; status?: number };
    err.code = body?.error;
    err.status = res.status;
    throw err;
  }
  return body as T;
}

export function isStateSubscribeEnabled(): boolean {
  return process.env.NEXT_PUBLIC_STATE_SUBSCRIBE_ENABLED === "true";
}

export async function signupForStateUpdates(
  email: string,
  state: string,
): Promise<SubscribeSignupResponse> {
  const res = await fetch(apiUrl("/api/v1/subscriptions/signup"), {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ email, state }),
  });
  return parseSubscribeJson(res);
}

export async function requestSubscribeCode(
  email: string,
  state: string,
): Promise<SubscribeSignupResponse> {
  const res = await fetch(apiUrl("/api/v1/subscriptions/request-code"), {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ email, state }),
  });
  return parseSubscribeJson(res);
}

export async function verifySubscribeCode(
  email: string,
  code: string,
): Promise<SubscribeVerifyResponse> {
  const res = await fetch(apiUrl("/api/v1/subscriptions/verify"), {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  });
  return parseSubscribeJson(res);
}

/** Dedupes React Strict Mode double-mount so one-time magic tokens aren't burned. */
const magicLinkInflight = new Map<string, Promise<SubscribeVerifyResponse>>();

export async function verifySubscribeMagicLink(
  token: string,
): Promise<SubscribeVerifyResponse> {
  const existing = magicLinkInflight.get(token);
  if (existing) return existing;

  const promise = (async () => {
    const res = await fetch(apiUrl("/api/v1/subscriptions/verify-link"), {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    return parseSubscribeJson<SubscribeVerifyResponse>(res);
  })();

  magicLinkInflight.set(token, promise);
  try {
    return await promise;
  } catch (err) {
    magicLinkInflight.delete(token);
    throw err;
  }
}

export async function subscribeToState(
  sessionToken: string,
  state: string,
): Promise<SubscribeStatesResponse> {
  const res = await fetch(apiUrl("/api/v1/subscriptions/subscribe"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${sessionToken}`,
    },
    body: JSON.stringify({ state, sessionToken }),
  });
  return parseSubscribeJson(res);
}

export async function unsubscribeFromState(
  sessionToken: string,
  state: string | "all",
): Promise<SubscribeStatesResponse> {
  const res = await fetch(apiUrl("/api/v1/subscriptions/unsubscribe"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${sessionToken}`,
    },
    body: JSON.stringify(
      state === "all" ? { all: true, sessionToken } : { state, sessionToken },
    ),
  });
  return parseSubscribeJson(res);
}
