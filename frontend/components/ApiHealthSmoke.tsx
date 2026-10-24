"use client";

import { useEffect, useState } from "react";
import {
  fetchPublicApiHealth,
  fetchPublicStates,
  fetchStateBills,
} from "@/lib/api/client";

type HealthState =
  | { status: "loading" }
  | {
      status: "ok";
      healthPayload: string;
      liveCount: number | null;
      mapStates: number | null;
      indigenousSponsorshipCount: number | null;
      sponsorshipFieldMissing: boolean;
    }
  | { status: "error"; message: string };

type ApiHealthSmokeProps = {
  /** Footer-adjacent dev banner: no section top margin. */
  placement?: "inline" | "banner";
};

export function ApiHealthSmoke({ placement = "inline" }: ApiHealthSmokeProps) {
  const marginClass = placement === "banner" ? "mt-0" : "mt-section";
  const [health, setHealth] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        const [healthRes, apiHealthRes, statesRes, sampleBillsRes] =
          await Promise.allSettled([
          fetch("/health-check").then(async (res) => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.text();
          }),
          fetchPublicApiHealth(),
          fetchPublicStates(),
          fetchStateBills("WA"),
        ]);

        if (cancelled) return;

        if (healthRes.status === "rejected") {
          throw healthRes.reason;
        }

        let liveCount: number | null = null;
        if (apiHealthRes.status === "fulfilled") {
          liveCount = apiHealthRes.value.liveCount;
        }

        let mapStates: number | null = null;
        if (statesRes.status === "fulfilled") {
          mapStates = Object.keys(statesRes.value.states).length;
          if (liveCount == null) {
            liveCount = statesRes.value.summary.passed
              + statesRes.value.summary.pending
              + statesRes.value.summary.rejected;
          }
        }

        let indigenousSponsorshipCount: number | null = null;
        if (apiHealthRes.status === "fulfilled") {
          indigenousSponsorshipCount =
            apiHealthRes.value.indigenousSponsorshipCount ?? null;
        }

        let sponsorshipFieldMissing = false;
        if (sampleBillsRes.status === "fulfilled") {
          const sample = sampleBillsRes.value.bills[0];
          sponsorshipFieldMissing = Boolean(
            sample && !("hasIndigenousSponsorship" in sample),
          );
        }

        setHealth({
          status: "ok",
          healthPayload: healthRes.value,
          liveCount,
          mapStates,
          indigenousSponsorshipCount,
          sponsorshipFieldMissing,
        });
      } catch (err: unknown) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Request failed";
          setHealth({ status: "error", message });
        }
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, []);

  if (health.status === "loading") {
    return (
      <p className={`${marginClass} text-body-md text-muted`} aria-live="polite">
        Checking Flask API via dev proxy…
      </p>
    );
  }

  if (health.status === "error") {
    return (
      <p
        className={`${marginClass} rounded-lg border border-status-pending/40 bg-status-pending/10 px-4 py-3 text-body-md text-status-pending`}
        role="status"
      >
        Flask API not reachable ({health.message}). Start Flask with{" "}
        <code className="font-mono">python app.py</code> (port 5000) or set{" "}
        <code className="font-mono">FLASK_DEV_URL</code> for Next rewrites.
      </p>
    );
  }

  return (
    <p
      className={`${marginClass} rounded-lg border border-accent/40 bg-accent/10 px-4 py-3 text-body-md text-accent`}
      role="status"
    >
      Flask OK (<code className="font-mono">/health-check</code>):{" "}
      <span className="font-mono">{health.healthPayload}</span>
      {health.liveCount != null ? (
        <>
          {" "}
          · Public API: <span className="font-mono">{health.liveCount}</span> Live
          bills
        </>
      ) : null}
      {health.mapStates != null ? (
        <>
          {" "}
          · <span className="font-mono">{health.mapStates}</span> map states
        </>
      ) : null}
      {health.indigenousSponsorshipCount != null ? (
        <>
          {" "}
          ·{" "}
          <span className="font-mono">{health.indigenousSponsorshipCount}</span>{" "}
          with Indigenous sponsorship
        </>
      ) : null}
      {health.sponsorshipFieldMissing ? (
        <>
          {" "}
          · Restart Flask to pick up{" "}
          <code className="font-mono">hasIndigenousSponsorship</code> in bill
          JSON (filters need it)
        </>
      ) : null}
    </p>
  );
}
