#!/bin/bash
# Backfill EO/proc discovery for newly enabled remaining-gap states on production.
set -euo pipefail

STATES=(MA WY)
LOG="${1:-/opt/policy-tracker/data/wave_remaining_eo_proc.log}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/policy-tracker}"

cd "$DEPLOY_PATH"
mkdir -p data

echo "=== Wave remaining EO/proc backfill $(date -Iseconds) ===" | tee -a "$LOG"

for ST in "${STATES[@]}"; do
  echo "" | tee -a "$LOG"
  echo "=== State $ST $(date -Iseconds) ===" | tee -a "$LOG"
  docker compose run --rm --no-deps \
    -v "$DEPLOY_PATH/sources/state_sources.json:/app/sources/state_sources.json" \
    -e LLM_BASE_URL=http://host.docker.internal:8080/v1 \
    -e LLM_MODEL=Qwen3.6-27B-Q8_0.gguf \
    -e LLM_REASONING=off \
    -e DISCOVERY_MAX_ANALYSES_PER_RUN=50 \
    scheduler python scripts/run_discovery.py \
      --skip-legiscan --skip-federal --state "$ST" \
      2>&1 | tee -a "$LOG"
  sleep 5
done

echo "=== Wave remaining complete $(date -Iseconds) ===" | tee -a "$LOG"
