#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker
CID=$(docker ps -aq --filter name=policy-tracker-scheduler-run | head -1)
echo "container=$CID"
if [ -n "$CID" ]; then
  docker logs "$CID" 2>&1 | tail -50
fi
