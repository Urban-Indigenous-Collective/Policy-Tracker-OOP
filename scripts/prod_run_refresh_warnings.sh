#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker
nohup docker compose exec -T scheduler python scripts/refresh_pending_validation_warnings.py --apply \
  > data/refresh_validation_warnings.log 2>&1 &
echo "refresh pid=$!"
