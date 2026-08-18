#!/bin/bash
# Synchronous fed-doj-news measurement run (foreground, logs to data/).
set -euo pipefail
cd /opt/policy-tracker
mkdir -p data
LOG="data/fed-doj-news-rerun-$(date -u +%Y%m%dT%H%M%SZ).log"
docker compose stop scheduler || true
docker compose build scheduler
docker compose run --rm --no-deps -T \
  -e LLM_BASE_URL=http://host.docker.internal:8080/v1 \
  -e LLM_MODEL=Qwen3.6-27B-Q8_0.gguf \
  -e LLM_REASONING=off \
  -e DISCOVERY_MAX_ANALYSES_PER_RUN=40 \
  scheduler python scripts/run_discovery.py \
  --skip-legiscan \
  --skip-state \
  --federal-source-id fed-doj-news \
  --max-analyses 40 \
  2>&1 | tee "$LOG"
echo "LOG=$LOG"
