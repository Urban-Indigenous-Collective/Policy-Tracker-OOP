#!/bin/bash
# Run document text cache backfill on production (background).
set -euo pipefail
cd /opt/policy-tracker
LOG="${1:-data/backfill_document_text_cache.log}"
nohup docker compose exec -T scheduler python scripts/backfill_document_text_cache.py \
  >> "$LOG" 2>&1 &
echo "document_text backfill pid=$! log=$LOG"
