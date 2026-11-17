# Phase 5 production cutover

**Status (2026-11-17):** Cutover executed. Cloudflare tunnel targets **nginx** (`http://nginx:80`), which serves Next for `/` and proxies `/api/` + webhooks to Flask. GitHub CD (`--profile tunnel`) builds and starts `web` + `frontend` + `nginx` + `tunnel` + `scheduler`.

## Live path

```text
Internet → Cloudflare Tunnel → nginx
                                 ├─ /api/*, /webhooks/*, /health-check, legacy analyzer → Flask
                                 └─ / → Next.js
```

## Do not

- Point the tunnel back at `http://web:8000` (that serves Flask JSON at `/`, not the map UI)
- Treat a successful `web`/`scheduler` restart alone as “frontend deployed” — confirm Next via home HTML or `docker compose ps` showing `frontend` + `nginx`

## Reference

[MMIP_FRONTEND_IMPLEMENTATION.md](./MMIP_FRONTEND_IMPLEMENTATION.md) — Phase 5.
