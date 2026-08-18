#!/bin/bash
# Launch fed-doj-news measurement run detached on production.
set -euo pipefail
cd /opt/policy-tracker
docker compose run --rm --no-deps -T scheduler python scripts/clear_justice_rejects.py
bash scripts/prod_rerun_fed_doj_news.sh
