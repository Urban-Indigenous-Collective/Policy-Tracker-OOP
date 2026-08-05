#!/bin/bash
# Ensure nightly discovery, status refresh, and deferred Slack digest are scheduled
# on the production scheduler container (persistent Docker service, not one-off runs).
set -euo pipefail

cd /opt/policy-tracker

touch .env
ensure_env() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    return 0
  fi
  echo "${key}=${value}" >> .env
  echo "Added ${key}=${value}"
}

ensure_env SLACK_DEFER_DISCOVERY true
ensure_env SLACK_SUMMARY_CRON "30 7 * * *"
ensure_env STATUS_REFRESH_ENABLED true
ensure_env STATUS_REFRESH_CRON "30 3 * * *"
ensure_env DISCOVERY_TZ America/New_York
ensure_env DISCOVERY_CRON "0 2 * * *"
ensure_env DISCOVERY_SLACK_ALWAYS true
ensure_env VALIDATION_REFRESH_ENABLED false
ensure_env VALIDATION_REFRESH_CRON "0 4 * * *"
ensure_env VALIDATION_REFRESH_APPLY_EVAL_EXPL_FIXES false

echo "=== Nightly schedule env ==="
grep -E '^(SLACK_DEFER|SLACK_SUMMARY|STATUS_REFRESH|DISCOVERY_TZ|DISCOVERY_CRON|DISCOVERY_SLACK|VALIDATION_REFRESH)' .env || true

echo "=== Starting scheduler (persistent service) ==="
docker compose up -d --no-deps scheduler
docker compose ps scheduler

echo "=== Registered cron jobs (from latest startup) ==="
docker compose logs scheduler 2>&1 | grep "Scheduler started:" | tail -1 || true

echo "=== Recent nightly job activity ==="
docker compose logs scheduler 2>&1 | grep -E "Starting scheduled (discovery|status refresh|indigenous|Slack)" | tail -10 || true

if docker ps --format '{{.Names}}' | grep -q 'policy-tracker-scheduler-run'; then
  echo "WARNING: one-off scheduler-run container still active (may compete for resources):"
  docker ps --format '{{.Names}} {{.Status}}' | grep scheduler-run || true
else
  echo "No competing one-off scheduler-run containers."
fi
