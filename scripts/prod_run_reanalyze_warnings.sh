#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker
nohup docker compose exec -T scheduler python scripts/reanalyze_pending_warnings.py "$@" \
  > data/reanalyze_pending_warnings.log 2>&1 &
echo "reanalyze pid=$!"
