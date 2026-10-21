"use client";

import { useEffect, useState } from "react";

type HealthState =
  | { status: "loading" }
  | { status: "ok"; payload: string }
  | { status: "error"; message: string };

export function ApiHealthSmoke() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetch("/health-check")
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const body = await res.text();
        if (!cancelled) {
          setHealth({ status: "ok", payload: body });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Request failed";
          setHealth({ status: "error", message });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (health.status === "loading") {
    return (
      <p className="mt-8 text-sm text-zinc-500" aria-live="polite">
        Checking Flask API via dev proxy…
      </p>
    );
  }

  if (health.status === "error") {
    return (
      <p
        className="mt-8 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        role="status"
      >
        Flask API not reachable ({health.message}). Start Flask on port 8000 or
        set <code className="font-mono">FLASK_DEV_URL</code> for Next rewrites.
      </p>
    );
  }

  return (
    <p
      className="mt-8 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
      role="status"
    >
      Flask API OK (proxied <code className="font-mono">/health-check</code>):{" "}
      <span className="font-mono">{health.payload}</span>
    </p>
  );
}
