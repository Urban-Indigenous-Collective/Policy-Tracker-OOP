#!/bin/bash
# Backfill EO/proc discovery for the 18 gap jurisdictions on production.
set -euo pipefail

STATES=(CO DC GA IA LA MS NE OH OR SC WV)
# KY and WY have honest EO/proc gaps — skip dedicated backfill
LOG="${1:-/opt/policy-tracker/data/wave_18_eo_proc.log}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/policy-tracker}"

cd "$DEPLOY_PATH"
mkdir -p data

echo "=== Wave 18 EO/proc backfill $(date -Iseconds) ===" | tee -a "$LOG"

for ST in "${STATES[@]}"; do
  echo "" | tee -a "$LOG"
  echo "=== State $ST $(date -Iseconds) ===" | tee -a "$LOG"
  docker compose run --rm --no-deps \
    -e LLM_BASE_URL=http://host.docker.internal:8080/v1 \
    -e LLM_MODEL=Qwen3.6-27B-Q8_0.gguf \
    -e LLM_REASONING=off \
    -e DISCOVERY_MAX_ANALYSES_PER_RUN=50 \
    scheduler python scripts/run_discovery.py \
      --skip-legiscan --skip-federal --state "$ST" \
      2>&1 | tee -a "$LOG"
  sleep 5
done

echo "=== Wave 18 complete $(date -Iseconds) ===" | tee -a "$LOG"
