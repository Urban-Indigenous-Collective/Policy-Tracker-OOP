# Policy Tracker

Flask app used by the [Urban Indigenous Collective](https://urbanindigenouscollective.org) to find, analyze, and review **MMIP-related** legislation, executive orders, and agency actions. LegiScan covers state bills; configured government sites cover federal and state pages that LegiScan does not index. Analysis runs through an OpenAI-compatible LLM (Ollama or llama-server). Reviewers work in Airtable (**Pending** → **Main v3**).

Public app: https://policy.urbanindigenouscollective.org

A clone with empty `.env.example` keys will start the Flask UI; LegiScan search, Airtable, and Slack stay inactive until you add your own credentials.

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Optional: LEGISCAN_KEY, AIRTABLE_*, SLACK_WEBHOOK_URL
# LLM defaults to local Ollama (see .env.example)

brew install poppler   # required for pdf2image OCR
ollama pull qwen2.5vl:32b

python app.py
# Open http://127.0.0.1:5000/analyzer
```

First startup scrapes Wikipedia to build the Indigenous politicians database (30–60s).

Run tests: `pytest tests/`

## Cutover timeline

Dates below come from git history (and, for Qwen3.6, from scripts in `deploy/` that are not yet a completed git-dated cutover).

| Date | Change |
|------|--------|
| 2026-04-15 | Initial Policy Tracker (API keys via environment variables). |
| 2026-08-01 | Bill analysis moved from OpenAI to local Ollama `qwen2.5vl:32b`. |
| 2026-08-01 | App moved off Render onto Docker + **Cloudflare Tunnel** on UIC’s self-hosted host. |
| 2026-08-01 | Nightly MMIP discovery pipeline (LegiScan + Pending workflow + Slack). |
| 2026-08-05 | Status refresh, Slack digests, ethnicity enrichment, one sequential nightly pipeline. |
| Prepared (see `deploy/`) | LLM cutover scripts: Ollama `qwen2.5vl:32b` → **Qwen3.6-27B Q8** on llama-server (`:8080`). |

Hosting today: Internet → Cloudflare Tunnel → Docker (gunicorn) on a private UIC host. Pushes to `main` deploy through GitHub Actions (`.github/workflows/deploy.yml`). Do not use ad-hoc rsync as the ship path.

## LLM

| Variable | Local default | Purpose |
|----------|---------------|---------|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible API (Ollama, vLLM, llama-server) |
| `LLM_MODEL` | `qwen2.5vl:32b` | Model name |
| `LLM_TEMPERATURE` | `0` | Deterministic inference |
| `LLM_SEED` | `42` | Reproducibility seed |
| `LLM_CACHE_ENABLED` | `true` | Cache analysis results on disk |

On the production Docker host, Ollama is typically `http://host.docker.internal:11434/v1`. After the Qwen3.6 cutover, llama-server is `http://host.docker.internal:8080/v1` (see `deploy/llm-cutover.env.snippet`). The production inference host is private (Tailscale); clones should keep the localhost default.

Cutover helpers (run on the GPU host, not from a laptop clone):

```bash
bash deploy/setup-qwen36-llama.sh    # download weights; do not load GPU
bash deploy/check-qwen36-ready.sh
bash deploy/cutover-qwen36-llama.sh  # unload Qwen2.5, start llama-server, rewrite .env
```

## Nightly MMIP discovery

Automated pipeline searches LegiScan and configured government sites, runs analysis, writes to Airtable **Pending**, and alerts Slack.

State and federal source manifests live in `sources/` (see [docs/STATE_SOURCES.md](docs/STATE_SOURCES.md) and [docs/FEDERAL_SOURCES.md](docs/FEDERAL_SOURCES.md)).

### Setup

1. Create the **Pending** table and add `Review Status` to **Main v3** — see [docs/AIRTABLE_PENDING_SCHEMA.md](docs/AIRTABLE_PENDING_SCHEMA.md).
2. Add to `.env`:
   - `SLACK_WEBHOOK_URL` — incoming webhook for the review channel
   - `AIRTABLE_PENDING_TABLE=Pending`
3. Bootstrap / merge state website links:
   ```bash
   python scripts/bootstrap_state_sources_agents.py
   python scripts/merge_state_manifests.py
   # Review sources/manifests/*.json — set review_needed=false on approved rows
   ```
4. Dry run:
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

The `scheduler` Docker service runs a nightly pipeline (default 2 AM ET) and approval sync every 10 minutes. The pipeline runs enabled steps sequentially: discovery → status refresh → validation refresh.

```bash
docker compose --profile tunnel up -d   # includes web + tunnel + scheduler
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `NIGHTLY_PIPELINE_CRON` | `0 2 * * *` | Nightly pipeline schedule (`DISCOVERY_CRON` is a deprecated alias) |
| `DISCOVERY_ENABLED` | `true` | Run discovery as pipeline step 1 |
| `STATUS_REFRESH_ENABLED` | `true` | Run LegiScan status refresh as pipeline step 2 |
| `VALIDATION_REFRESH_ENABLED` | `false` | Run pending validation refresh as pipeline step 3 |
| `DISCOVERY_TZ` | `America/New_York` | Timezone for cron |
| `APPROVAL_SYNC_INTERVAL_MIN` | `10` | How often to sync Airtable status changes |
| `DISCOVERY_MAX_ANALYSES_PER_RUN` | `25` | Cap LLM analyses per run (safety valve) |
| `DISCOVERY_RELEVANCE_MIN_CONFIDENCE` | `0.6` | MMIP relevance gate threshold |
| `SLACK_QUIET_RUNS` | `true` | Suppress Slack when no new policies found |

## GitHub Actions CD

Pushes to `main` deploy via `.github/workflows/deploy.yml`. Required repository secrets (not needed for a local clone): `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PATH`, `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`.

## Dependencies

- Direct deps listed in `requirements.in`
- Pinned lockfile: `requirements.txt` (regenerate with `pip install -r requirements.in && pip freeze > requirements.txt`)
- Audit: `pip-audit`

## Security notes

- Never commit `.env` or `cloudflared/credentials.json` (see `.env.example`)
- Rotate any API keys that were ever committed to git
- LegiScan and Airtable calls need keys in your local `.env`; they are not in this repository
