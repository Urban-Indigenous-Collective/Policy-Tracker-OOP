#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker
docker compose build scheduler
docker compose run --rm --no-deps -T scheduler python scripts/clear_justice_rejects.py
