#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker
echo "=== host data logs ==="
ls -la data/ | tail -10 || true
echo "=== docker runs ==="
docker ps -a --format '{{.Names}} {{.Status}}' | grep scheduler-run | tail -5 || true
echo "=== recent nohup ==="
ps aux | grep run_discovery | grep -v grep || true
