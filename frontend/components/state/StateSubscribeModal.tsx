"use client";

import { useEffect, useId, useState } from "react";

import { NATIONAL_STATE_CODE } from "@/lib/api/state-code";
import {
  requestSubscribeCode,
  signupForStateUpdates,
  subscribeToState,
  unsubscribeFromState,
  verifySubscribeCode,
} from "@/lib/api/subscriptions";
import { STATE_NAMES } from "@/lib/map/state-codes";

type Step = "email" | "otp" | "manage" | "done";

type StateSubscribeModalProps = {
  stateCode: string;
  open: boolean;
  onClose: () => void;
};

function stateLabel(code: string): string {
  if (code === NATIONAL_STATE_CODE) return "National";
  return STATE_NAMES[code] ?? code;
}

export function StateSubscribeModal({
  stateCode,
  open,
  onClose,
}: StateSubscribeModalProps) {
  const titleId = useId();
  const emailId = useId();
  const codeId = useId();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const [states, setStates] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [offerManage, setOfferManage] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStep("email");
    setEmail("");
    setCode("");
    setSessionToken("");
    setStates([]);
    setBusy(false);
    setError(null);
    setStatusMessage(null);
    setOfferManage(false);
  }, [open, stateCode]);

  if (!open) return null;

  const currentLabel = stateLabel(stateCode);
  const subscribedToCurrent = states.includes(stateCode);

  async function onSignup(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await signupForStateUpdates(email.trim(), stateCode);
      setEmail(result.email);
      setStates(result.states ?? [stateCode]);
      const newlyAdded = Boolean(result.added);
      const knownEmail = Boolean(result.hasExistingSubscriptions);
      setOfferManage(knownEmail);
      if (newlyAdded && !knownEmail) {
        setStatusMessage(`You're subscribed to updates for ${currentLabel}.`);
      } else if (newlyAdded && knownEmail) {
        setStatusMessage(
          `You've subscribed to updates for ${currentLabel}. We can see this email already exists — would you like to manage your existing subscriptions?`,
        );
      } else {
        // Truly already on this state's list (idempotent re-submit).
        setStatusMessage(
          knownEmail
            ? `You're already subscribed to updates for ${currentLabel}. Would you like to manage your existing subscriptions?`
            : `You're already subscribed to updates for ${currentLabel}.`,
        );
      }
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not subscribe");
    } finally {
      setBusy(false);
    }
  }

  async function onStartManage() {
    setBusy(true);
    setError(null);
    try {
      await requestSubscribeCode(email, stateCode);
      setStep("otp");
      setStatusMessage(
        "Enter the verification code we emailed you to manage or unsubscribe.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send verification code");
    } finally {
      setBusy(false);
    }
  }

  async function onResendCode() {
    setBusy(true);
    setError(null);
    try {
      await requestSubscribeCode(email, stateCode);
      setStatusMessage("A new verification code was sent.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend code");
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await verifySubscribeCode(email, code.trim());
      setSessionToken(result.sessionToken);
      setStates(result.states);
      setStep("manage");
      setStatusMessage(
        "Email verified. Manage your state subscriptions below, or unsubscribe.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSubscribeCurrent() {
    setBusy(true);
    setError(null);
    try {
      const result = await subscribeToState(sessionToken, stateCode);
      setStates(result.states);
      setStatusMessage(`Subscribed to ${currentLabel}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not subscribe");
    } finally {
      setBusy(false);
    }
  }

  async function onUnsubscribe(target: string | "all") {
    setBusy(true);
    setError(null);
    try {
      const result = await unsubscribeFromState(sessionToken, target);
      setStates(result.states);
      if (target === "all" || result.states.length === 0) {
        setStatusMessage("You are unsubscribed from all state updates.");
        setStep("done");
        setOfferManage(false);
      } else {
        setStatusMessage(`Unsubscribed from ${stateLabel(String(target))}.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unsubscribe");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[120] flex items-end justify-center bg-black/60 p-4 sm:items-center"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md border border-surface-border bg-background p-drawer-x py-6 text-foreground shadow-lg"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3 id={titleId} className="font-mono text-sm font-bold uppercase tracking-wide">
            {step === "done" ? "Subscription updated" : `Updates · ${currentLabel}`}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer text-sm text-muted outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-foreground/25"
          >
            Close
          </button>
        </div>

        {statusMessage ? (
          <p className="mb-3 text-sm text-muted" aria-live="polite">
            {statusMessage}
          </p>
        ) : null}
        {error ? (
          <p className="mb-3 text-sm text-red-400" role="alert">
            {error}
          </p>
        ) : null}

        {step === "email" ? (
          <form onSubmit={onSignup} className="flex flex-col gap-3">
            <label htmlFor={emailId} className="text-xs uppercase tracking-wide text-muted">
              Email
            </label>
            <input
              id={emailId}
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="h-10 border border-surface-border bg-transparent px-3 text-sm outline-none focus-visible:ring-1 focus-visible:ring-foreground/25"
              placeholder="you@example.org"
            />
            <p className="text-xs text-muted">
              Subscribe right away. Managing or unsubscribing an existing address
              requires a verification code.
            </p>
            <button
              type="submit"
              disabled={busy}
              className="mt-2 h-10 cursor-pointer border border-foreground bg-transparent text-xs font-semibold uppercase tracking-wide outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-foreground/25 disabled:opacity-50"
            >
              {busy ? "Saving…" : "Subscribe"}
            </button>
          </form>
        ) : null}

        {step === "otp" ? (
          <form onSubmit={onVerify} className="flex flex-col gap-3">
            <label htmlFor={codeId} className="text-xs uppercase tracking-wide text-muted">
              Verification code
            </label>
            <input
              id={codeId}
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              required
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              className="h-10 border border-surface-border bg-transparent px-3 font-mono text-sm tracking-[0.3em] outline-none focus-visible:ring-1 focus-visible:ring-foreground/25"
              placeholder="······"
            />
            <button
              type="submit"
              disabled={busy || code.length !== 6}
              className="mt-2 h-10 cursor-pointer border border-foreground bg-transparent text-xs font-semibold uppercase tracking-wide outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-foreground/25 disabled:opacity-50"
            >
              {busy ? "Verifying…" : "Verify email"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onResendCode}
              className="cursor-pointer text-left text-xs uppercase tracking-wide text-muted outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-foreground/25 disabled:opacity-50"
            >
              Resend code
            </button>
          </form>
        ) : null}

        {step === "manage" ? (
          <div className="flex flex-col gap-4">
            {!subscribedToCurrent ? (
              <button
                type="button"
                disabled={busy}
                onClick={onSubscribeCurrent}
                className="h-10 cursor-pointer border border-foreground bg-transparent text-xs font-semibold uppercase tracking-wide outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-foreground/25 disabled:opacity-50"
              >
                {busy ? "Saving…" : `Subscribe to ${currentLabel}`}
              </button>
            ) : (
              <p className="text-sm">You are subscribed to {currentLabel}.</p>
            )}

            {states.length > 0 ? (
              <div className="flex flex-col gap-2">
                <p className="text-xs uppercase tracking-wide text-muted">Your states</p>
                <ul className="flex flex-col gap-2">
                  {states.map((code) => (
                    <li
                      key={code}
                      className="flex items-center justify-between gap-3 border border-surface-border px-3 py-2 text-sm"
                    >
                      <span>{stateLabel(code)}</span>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => onUnsubscribe(code)}
                        className="cursor-pointer text-xs uppercase tracking-wide text-muted outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-foreground/25 disabled:opacity-50"
                      >
                        Unsubscribe
                      </button>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onUnsubscribe("all")}
                  className="mt-1 cursor-pointer text-left text-xs uppercase tracking-wide text-muted outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-foreground/25 disabled:opacity-50"
                >
                  Unsubscribe from all
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        {step === "done" ? (
          <div className="mt-2 flex flex-col gap-2">
            {offerManage ? (
              <button
                type="button"
                disabled={busy}
                onClick={onStartManage}
                className="h-10 w-full cursor-pointer border border-foreground bg-transparent text-xs font-semibold uppercase tracking-wide outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-foreground/25 disabled:opacity-50"
              >
                {busy ? "Sending code…" : "Manage existing subscriptions"}
              </button>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              className="h-10 w-full cursor-pointer border border-surface-border bg-transparent text-xs font-semibold uppercase tracking-wide text-muted outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-foreground/25"
            >
              Done
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
