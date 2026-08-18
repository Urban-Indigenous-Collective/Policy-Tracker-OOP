#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker/data
ls -lt fed-doj-news-rerun*.log 2>/dev/null | head -3 || true
LATEST=$(ls -t fed-doj-news-rerun*.log 2>/dev/null | head -1 || true)
if [ -n "$LATEST" ]; then
  echo "=== tail $LATEST ==="
  tail -40 "$LATEST"
fi
docker ps --format '{{.Names}} {{.Status}}' | grep scheduler-run || true
