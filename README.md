# Policy Tracker

Flask app for processing LegiScan bills and executive orders with local Qwen analysis via Ollama, deployed on UIC's self-hosted server via Docker and Cloudflare Tunnel.

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with LEGISCAN_KEY, AIRTABLE_* keys, and Ollama settings

brew install poppler   # required for pdf2image OCR
ollama pull qwen2.5vl:32b

python app.py
# Open http://127.0.0.1:5000/analyzer
```

First startup scrapes Wikipedia to build the Indigenous politicians database (30–60s).

## Production architecture

```text
Internet → Cloudflare Tunnel → Docker (gunicorn :8000) on 100.71.124.8 (WSL)
GitHub push → Tailscale → SSH/rsync → docker compose up
```

Public URL: https://policy.urbanindigenouscollective.org

## LLM (provider-agnostic)

Policy Tracker uses structured JSON analysis via a pluggable LLM backend:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible API (Ollama, vLLM, etc.) |
| `LLM_MODEL` | `qwen2.5vl:32b` | Model name |
| `LLM_TEMPERATURE` | `0` | Deterministic inference |
| `LLM_SEED` | `42` | Reproducibility seed |
| `LLM_CACHE_ENABLED` | `true` | Cache analysis results on disk |

For Docker on the server, point at the host running Ollama:

```bash
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

Optional shared gateway for multiple apps (wocconwaker, etc.):

```bash
docker compose --profile gateway up -d
LLM_GATEWAY_URL=http://inference-gateway:8090
```

Run tests: `pytest tests/`

## Nightly MMIP discovery

Automated pipeline searches LegiScan and configured state websites for new MMIP policy, runs the UIC analysis, writes to Airtable **Pending**, and alerts Slack.

### Setup

1. Create the **Pending** table and add `Review Status` to **Main v3** — see [docs/AIRTABLE_PENDING_SCHEMA.md](docs/AIRTABLE_PENDING_SCHEMA.md).
2. Add to `.env`:
   - `SLACK_WEBHOOK_URL` — incoming webhook for the review channel
   - `AIRTABLE_PENDING_TABLE=Pending`
3. Bootstrap state website links from existing Airtable entries:
   ```bash
   python scripts/bootstrap_state_sources.py
   # Edit sources/state_sources.json — point URLs at index pages, set review_needed=false
   ```
4. Tune the relevance gate with a dry run:
   ```bash
   python scripts/run_discovery.py --dry-run --legiscan-only
   ```

### Manual run

```bash
python scripts/run_discovery.py              # full discovery
python scripts/run_discovery.py --legiscan-only
python scripts/run_discovery.py --dry-run
python approval_sync.py                      # sync approved/send-back records
```

### Scheduler (production)

The `scheduler` Docker service runs discovery nightly (default 2 AM ET) and approval sync every 10 minutes:

```bash
docker compose --profile tunnel up -d   # includes web + tunnel + scheduler
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `DISCOVERY_CRON` | `0 2 * * *` | Nightly discovery schedule |
| `DISCOVERY_TZ` | `America/New_York` | Timezone for cron |
| `APPROVAL_SYNC_INTERVAL_MIN` | `10` | How often to sync Airtable status changes |
| `DISCOVERY_MAX_ANALYSES_PER_RUN` | `25` | Cap LLM analyses per run (safety valve) |
| `DISCOVERY_RELEVANCE_MIN_CONFIDENCE` | `0.6` | MMIP relevance gate threshold |
| `SLACK_QUIET_RUNS` | `true` | Suppress Slack when no new policies found |

## Deploy manually

```bash
# One-time on server (WSL at /opt/policy-tracker):
#   .env with production secrets
#   cloudflared/credentials.json for policy-uic tunnel

./deploy/deploy.sh
```

## Cloudflare Worker (Render → self-hosted cutover)

The `render-redirect` Worker previously proxied to Render and returned `{"status":"waiting"}` when cold. After migrating to the tunnel, update it to passthrough:

```bash
# Add CLOUDFLARE_API_TOKEN to .env (Workers Scripts:Edit)
./scripts/deploy-worker.sh
```

Or delete the Worker route `policy.urbanindigenouscollective.org/*` in the Cloudflare dashboard.

## GitHub Actions CD

Pushes to `main` deploy via `.github/workflows/deploy.yml`.

Required secrets (copied from UIC-Learning):

| Secret | Value |
|--------|-------|
| `DEPLOY_SSH_KEY` | `~/.ssh/uic-learning-deploy` private key |
| `DEPLOY_HOST` | `100.71.124.8` |
| `DEPLOY_USER` | `info@urbanindigenouscollective.org` |
| `DEPLOY_PATH` | `C:/Users/info/policy-tracker` |
| `TS_OAUTH_CLIENT_ID` | Tailscale OAuth client (tag:ci) |
| `TS_OAUTH_SECRET` | Tailscale OAuth secret |

## Dependencies

- Direct deps listed in `requirements.in`
- Pinned lockfile: `requirements.txt` (regenerate with `pip install -r requirements.in && pip freeze > requirements.txt`)
- Audit: `pip-audit`

## Security notes

- Never commit `.env` (see `.env.example`)
- Rotate any API keys that were ever committed to git
- Render service can be disabled after tunnel cutover is verified
