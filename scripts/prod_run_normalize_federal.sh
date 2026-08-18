#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker
docker compose exec -T scheduler python scripts/normalize_pending_federal_state.py "$@"
