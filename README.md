# Policy Tracker

Flask app for processing LegiScan bills and executive orders with OpenAI-assisted analysis, deployed on UIC's self-hosted server via Docker and Cloudflare Tunnel.

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with LEGISCAN_KEY, OPENAI_API_KEY, AIRTABLE_* keys

brew install poppler   # required for pdf2image OCR

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
