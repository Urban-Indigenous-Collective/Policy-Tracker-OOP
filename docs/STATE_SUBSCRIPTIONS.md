# State update subscriptions

Env-gated feature: visitors subscribe to MMIP policy updates **by state** from the map drawer or policy list (bell control).

## Phase 1 — complete (current)

| Piece | Status |
|-------|--------|
| Env flags `STATE_SUBSCRIBE_ENABLED` + `NEXT_PUBLIC_STATE_SUBSCRIBE_ENABLED` | Done |
| Bell UI (drawer + policy list) | Done |
| Local JSON store (`data/state_subscriptions.json`) | Done |
| Signup always adds the state (no OTP), even if email already exists | Done |
| OTP only when user chooses manage / unsubscribe | Done |
| Magic link on OTP email → `/subscribe/manage` | Done |
| Design-system HTML email templates (welcome, OTP, digest shell) | Done |
| Mail delivery | **Gmail as `info@`** (or `log` for local without SA) |

**Local enable:** set both flags `true`, put `NEXT_PUBLIC_*` in `frontend/.env.local`, restart Flask + Next.

**Real email (recommended for e2e):** same Gmail API path as UIC membership (`gmail.send` via Workspace SA):

```bash
STATE_SUBSCRIBE_MAIL_PROVIDER=gmail
STATE_SUBSCRIBE_MAIL_FROM=Urban Indigenous Collective <info@urbanindigenouscollective.org>
STATE_SUBSCRIBE_GMAIL_SA_KEY_PATH=~/.config/gmail-migration/service-account.json
PUBLIC_SITE_URL=http://127.0.0.1:3000   # so magic links hit local Next
# Optional: HTTP fallback for logo/img src in non-Gmail renders (Gmail CID-inlines the logo)
# STATE_SUBSCRIBE_EMAIL_ASSET_ORIGIN=https://policy.urbanindigenouscollective.org
```

Gmail delivery attaches `frontend/public/brand/uic-logo-email.png` as an inline `cid:logo` image so the mark shows even when `PUBLIC_SITE_URL` is localhost and prod `/brand` is not yet served by Next.

With `log`, OTP codes and magic links appear in the Flask log instead.

## Phase 2 — send real email

**Goal:** Deliver welcome + manage OTP (and later manage links) through Gmail as `info@urbanindigenouscollective.org`.

1. **Template polish** — HTML lives in [`subscriptions/templates/`](../subscriptions/templates/); brand colors in [`subscriptions/email_brand.py`](../subscriptions/email_brand.py) (mirrored from `frontend/lib/design/tokens.css`). Preview by rendering in tests or a small script; adjust copy/spacing against the live site.
2. **Provider** — Set:
   - `STATE_SUBSCRIBE_MAIL_PROVIDER=gmail`
   - `STATE_SUBSCRIBE_MAIL_FROM=Urban Indigenous Collective <info@urbanindigenouscollective.org>`
   - `STATE_SUBSCRIBE_GMAIL_SA_KEY_PATH=~/.config/gmail-migration/service-account.json` (or inline `STATE_SUBSCRIBE_GMAIL_SA_KEY`)
   - Uses the same service account + domain-wide `gmail.send` delegation as UIC-Core-Services `membership/worker/gmail.ts`
3. **Manage link** — OTP email includes a one-time magic URL (`/subscribe/manage?token=…`). Keep OTP as fallback from the bell.
4. **Airtable (optional)** — Still undecided; if needed for analytics, sync subscriber email + states out of band. Do not block sending on Airtable.

## Phase 3 — digests (implemented)

Morning emails ride the same job as the deferred Slack summary (`SLACK_SUMMARY_CRON`, default **7:30am ET**).

| Piece | Behavior |
|-------|----------|
| **Queue** | `data/pending_subscriber_digest.json` via [`subscriptions/digest_queue.py`](../subscriptions/digest_queue.py) |
| **New Live** | Pending→Live in [`approval_sync.py`](../approval_sync.py) enqueues `kind=new_live` (not Pending discovery) |
| **Status update** | Live-only LegiScan refresh changes where field is **Status** or **Progression** |
| **Send** | [`subscriptions/digest.py`](../subscriptions/digest.py) `send_morning_digests()` from [`scheduler.py`](../scheduler.py) `run_slack_summary_job` |
| **Fan-out** | One email per subscriber listing that window’s items for their states |
| **Idempotency** | Event keys in store `digest_notified` + queue dedupe |
| **Gate** | `STATE_SUBSCRIBE_ENABLED`; mail via `STATE_SUBSCRIBE_MAIL_PROVIDER` |

Daytime Live approvals queue for the **next** 7:30 digest (no instant email). Chamber / Last Update / overview-link-only edits do not alert.

## API (Phase 1)

See [API_V1.md](API_V1.md#state-subscriptions-optional). Primary entry: `POST /api/v1/subscriptions/signup`.

## Out of scope (for now)

- User accounts / passwords
- SMS
- Per-bill instant alerts (unless Phase 3 explicitly chooses that)
