#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker
docker cp scripts/fix_savanna_pending_names.py policy-tracker-scheduler-1:/app/scripts/fix_savanna_pending_names.py
docker cp scripts/refresh_pending_validation_warnings.py policy-tracker-scheduler-1:/app/scripts/refresh_pending_validation_warnings.py
docker compose exec -T scheduler python scripts/fix_savanna_pending_names.py --apply
nohup docker compose exec -T scheduler python scripts/refresh_pending_validation_warnings.py --apply \
  > data/refresh_validation_warnings.log 2>&1 &
echo "refresh pid=$!"
sleep 2
tail -3 data/refresh_validation_warnings.log || true
