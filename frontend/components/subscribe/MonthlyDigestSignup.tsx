"use client";

import { useId, useState, type FormEvent, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";

import {
  isStateSubscribeEnabled,
  signupForMonthlyDigest,
} from "@/lib/api/subscriptions";

const LEARN_MORE_HREF = "https://urbanindigenouscollective.org";

type MonthlyDigestSignupProps = {
  /** Footer logo column (same slot as original mission row). */
  logo: ReactNode;
};

/**
 * Footer mission + CTA slot. Map home (subscriptions on): monthly digest copy +
 * email + Subscribe. Otherwise: original Serving… / learn more. Layout matches
 * SiteFooter mission stack — only the content strings/controls change.
 */
export function MonthlyDigestSignup({ logo }: MonthlyDigestSignupProps) {
  const pathname = usePathname();
  const emailId = useId();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const showDigest = isStateSubscribeEnabled() && pathname === "/";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await signupForMonthlyDigest(email.trim());
      setEmail(result.email);
      setSuccess(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not subscribe");
    } finally {
      setBusy(false);
    }
  }

  if (!showDigest) {
    return (
      <div className="flex flex-col gap-footer-mission-stack">
        <div className="flex flex-col gap-footer-mission-stack lg:flex-row lg:items-start lg:justify-between lg:gap-footer-top">
          <p className="uic-footer-mission max-w-footer-mission shrink-0">
            Serving Indigenous individuals from North, Central, and South
            America, the Caribbean, and Pacific Islands
          </p>
          {logo}
        </div>
        <Link href={LEARN_MORE_HREF} className="uic-footer-learn">
          learn more
        </Link>
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-col gap-footer-mission-stack"
      aria-labelledby="monthly-digest-heading"
    >
      <div className="flex flex-col gap-footer-mission-stack lg:flex-row lg:items-start lg:justify-between lg:gap-footer-top">
        <div className="flex max-w-footer-mission shrink-0 flex-col gap-footer-cta-stack">
          <p id="monthly-digest-heading" className="uic-footer-mission">
            Get a monthly summary of everything happening with MMIP policy
          </p>
          {success ? (
            <p className="font-sans text-sm text-muted" role="status">
              {success}
            </p>
          ) : (
            <div>
              <label htmlFor={emailId} className="sr-only">
                Email address
              </label>
              <input
                id={emailId}
                type="email"
                name="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={busy}
                placeholder="Email address"
                className="w-full border-0 border-b border-footer-divider bg-transparent pb-3 font-sans text-base text-foreground outline-none placeholder:text-muted focus-visible:border-accent disabled:opacity-60"
              />
            </div>
          )}
        </div>
        {logo}
      </div>
      {!success ? (
        <>
          <button type="submit" disabled={busy} className="uic-footer-learn">
            {busy ? "…" : "Subscribe"}
          </button>
          {error ? (
            <p className="font-sans text-sm text-muted" role="alert">
              {error}
            </p>
          ) : null}
        </>
      ) : null}
    </form>
  );
}
