"use client";

import Image from "next/image";
import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  unsubscribeFromState,
  verifySubscribeMagicLink,
} from "@/lib/api/subscriptions";
import { NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import { STATE_NAMES } from "@/lib/map/state-codes";

const SESSION_KEY = "pt-subscribe-manage-session";

type ManageSession = {
  sessionToken: string;
  email: string;
  states: string[];
};

function stateLabel(code: string): string {
  if (code === NATIONAL_STATE_CODE) return "National";
  return STATE_NAMES[code] ?? code;
}

function readCachedSession(): ManageSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ManageSession;
    if (
      typeof parsed?.sessionToken === "string" &&
      typeof parsed?.email === "string" &&
      Array.isArray(parsed?.states)
    ) {
      return parsed;
    }
  } catch {
    /* ignore */
  }
  return null;
}

function writeCachedSession(session: ManageSession) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    /* ignore */
  }
}

function ManageSubscriptionsInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token")?.trim() ?? "";
  const isPreview = searchParams.get("preview") === "1";

  const [status, setStatus] = useState<"loading" | "ready" | "error" | "done">(
    "loading",
  );
  const [error, setError] = useState<string | null>(null);
  const [sessionToken, setSessionToken] = useState("");
  const [email, setEmail] = useState("");
  const [states, setStates] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isPreview) {
      setSessionToken("preview");
      setEmail("preview@example.com");
      setStates(["WA", "OR"]);
      setStatus("ready");
      setMessage("Preview mode — sample subscriptions (not live).");
      return;
    }

    const cached = readCachedSession();
    if (cached && !token) {
      setSessionToken(cached.sessionToken);
      setEmail(cached.email);
      setStates(cached.states);
      setStatus(cached.states.length === 0 ? "done" : "ready");
      setMessage(
        cached.states.length === 0
          ? "You are unsubscribed from all state updates."
          : "Email verified. Manage your state subscriptions below.",
      );
      return;
    }

    if (!token) {
      setStatus("error");
      setError("Missing manage link token.");
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const result = await verifySubscribeMagicLink(token);
        if (cancelled) return;
        const next: ManageSession = {
          sessionToken: result.sessionToken,
          email: result.email,
          states: result.states,
        };
        writeCachedSession(next);
        setSessionToken(next.sessionToken);
        setEmail(next.email);
        setStates(next.states);
        setStatus("ready");
        setMessage("Email verified. Manage your state subscriptions below.");
        // Drop one-time token from the URL so refresh / reopen still works.
        router.replace("/subscribe/manage");
      } catch (err) {
        if (cancelled) return;
        // Token already used — reuse session from the first successful open.
        const fallback = readCachedSession();
        if (fallback) {
          setSessionToken(fallback.sessionToken);
          setEmail(fallback.email);
          setStates(fallback.states);
          setStatus(fallback.states.length === 0 ? "done" : "ready");
          setMessage(
            fallback.states.length === 0
              ? "You are unsubscribed from all state updates."
              : "Email verified. Manage your state subscriptions below.",
          );
          router.replace("/subscribe/manage");
          return;
        }
        setStatus("error");
        setError(err instanceof Error ? err.message : "Could not verify link");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, isPreview, router]);

  const sortedStates = useMemo(() => [...states].sort(), [states]);

  async function onUnsubscribe(target: string | "all") {
    if (isPreview || sessionToken === "preview") {
      const nextStates =
        target === "all" ? [] : states.filter((code) => code !== target);
      setStates(nextStates);
      if (nextStates.length === 0) {
        setMessage("You are unsubscribed from all state updates.");
        setStatus("done");
      } else {
        setMessage(`Unsubscribed from ${stateLabel(String(target))}.`);
      }
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const result = await unsubscribeFromState(sessionToken, target);
      const next: ManageSession = {
        sessionToken,
        email,
        states: result.states,
      };
      writeCachedSession(next);
      setStates(result.states);
      if (target === "all" || result.states.length === 0) {
        setMessage("You are unsubscribed from all state updates.");
        setStatus("done");
      } else {
        setMessage(`Unsubscribed from ${stateLabel(String(target))}.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unsubscribe");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-md border border-surface-border bg-background">
      <div className="h-[3px] bg-accent" aria-hidden />
      <div className="px-7 pb-7 pt-10">
        <Image
          src="/brand/uic-logo-email.png"
          alt="Urban Indigenous Collective"
          width={53}
          height={72}
          className="h-[72px] w-auto"
          style={{ width: "auto", height: 72 }}
          priority
        />
        <p className="mt-3 font-mono text-xs font-bold uppercase tracking-[0.2em] text-accent">
          MMIP Policy Tracker
        </p>
        <h1 className="mt-3 font-mono text-xl font-bold uppercase tracking-wide">
          Manage subscriptions
        </h1>

        {status === "loading" ? (
          <p className="mt-6 text-sm text-muted">Verifying your link…</p>
        ) : null}

        {message ? (
          <p className="mt-4 text-sm text-muted" aria-live="polite">
            {message}
          </p>
        ) : null}
        {error ? (
          <p className="mt-4 text-sm text-red-400" role="alert">
            {error}
          </p>
        ) : null}

        {status === "ready" ? (
          <div className="mt-6 flex flex-col gap-4">
            <p className="text-sm text-muted">{email}</p>
            {sortedStates.length > 0 ? (
              <ul className="flex flex-col gap-2">
                {sortedStates.map((code) => (
                  <li
                    key={code}
                    className="flex items-center justify-between gap-3 border border-surface-border px-3 py-2 text-sm"
                  >
                    <span>{stateLabel(code)}</span>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onUnsubscribe(code)}
                      className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-foreground/25 disabled:opacity-50"
                    >
                      Unsubscribe
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm">No active state subscriptions.</p>
            )}
            <button
              type="button"
              disabled={busy || sortedStates.length === 0}
              onClick={() => onUnsubscribe("all")}
              className="h-10 cursor-pointer border border-foreground bg-transparent text-xs font-semibold uppercase tracking-wide outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-foreground/25 disabled:opacity-50"
            >
              Unsubscribe from all
            </button>
          </div>
        ) : null}

        {status === "done" || status === "error" || status === "ready" ? (
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/"
              className="inline-flex h-10 items-center border border-foreground px-4 text-xs font-semibold uppercase tracking-wide outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-foreground/25"
            >
              Back to map
            </Link>
            <Link
              href="/policy-list"
              className="inline-flex h-10 items-center border border-surface-border px-4 text-xs font-semibold uppercase tracking-wide text-muted outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-foreground/25"
            >
              Policy list
            </Link>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function ManageSubscriptionsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto w-full max-w-md border border-surface-border px-7 py-10 text-sm text-muted">
          Loading…
        </div>
      }
    >
      <ManageSubscriptionsInner />
    </Suspense>
  );
}
