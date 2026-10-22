# MMIP Policy Tracker — Next.js frontend

Public UI for the MMIP Policy Tracker (App Router, TypeScript, Tailwind).

Master implementation plan: [../docs/MMIP_FRONTEND_IMPLEMENTATION.md](../docs/MMIP_FRONTEND_IMPLEMENTATION.md).

## Prerequisites

- Node.js 22+ (see `.nvmrc`)
- Policy Tracker Flask running locally (**port 5000** via `python app.py`, or **8002** via `docker compose up web`)

## Development

From repo root (convenience `package.json`):

```bash
cd frontend && npm install
cd .. && npm run dev
```

Or from `frontend/` only: `npm run dev`.

Open [http://localhost:3000](http://localhost:3000). The placeholder page calls `/health-check`, which Next rewrites to Flask.

### Environment

| Variable | Purpose |
|----------|---------|
| `FLASK_DEV_URL` | Rewrite target for `/api/*` and `/health-check` (default `http://127.0.0.1:5000` = `python app.py`) |
| `NEXT_PUBLIC_SITE_URL` | Public site URL for metadata (Phase 4+) |
| `NEXT_PUBLIC_API_BASE` | Browser API prefix; empty = same-origin `/api` behind nginx in prod |
| `INTERNAL_API_BASE` | Server-side fetch target for SSR (`http://web:8000` in Docker frontend service; Mac dev uses `FLASK_DEV_URL` fallback) |

Copy root `.env.example` for shared backend secrets; frontend-only vars can live in `frontend/.env.local`.

## Production-shaped Docker (optional profile)

From repo root:

```bash
docker compose --profile frontend up --build
```

Nginx listens on **`${PUBLIC_HOST_PORT:-8095}`** (not 8080 — that port is often used by local llama-server/Qwen on this project).

```bash
docker compose --profile frontend up --build
# → http://localhost:8095
```

If 8095 is taken too, set in repo root `.env`: `PUBLIC_HOST_PORT=8888` (or any free port).

Flask alone is still published as **`${POLICY_HOST_PORT:-8002}`** → container `:8000`. You do not need host `:8000` for compose.

Default deploy (no profile) is unchanged: tunnel → Flask only until Phase 5 cutover.

### Local Next dev (without Docker)

```bash
# If Flask is from compose on 8002:
FLASK_DEV_URL=http://127.0.0.1:8002 npm run dev
```

## Public API smoke (Phase 2+)

With Flask running and Airtable env configured:

```bash
# Terminal 1: Flask (port 5000)
source .venv/bin/activate && python app.py

# Terminal 2:
python3 scripts/smoke_public_api.py
# Docker web instead: SMOKE_API_BASE=http://127.0.0.1:8002 python3 scripts/smoke_public_api.py
```

See [../docs/API_V1.md](../docs/API_V1.md). Dev footer banner also calls `/api/v1/health` and `/api/v1/states` via Next rewrites.

## Scripts

- `npm run dev` — Next dev server
- `npm run build` — production build
- `npm run start` — production server (port 3000)
- `npm run lint` — ESLint
