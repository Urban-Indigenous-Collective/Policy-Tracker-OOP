#!/bin/bash
# Run discovery once on the production server (called via SSH/WSL).
set -euo pipefail
cd /opt/policy-tracker
docker compose run --rm --no-deps scheduler python scripts/run_discovery.py "$@"
