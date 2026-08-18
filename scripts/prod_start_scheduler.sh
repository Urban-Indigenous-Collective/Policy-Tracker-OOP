#!/bin/bash
cd /opt/policy-tracker
# --no-deps: scheduler must run even when web healthcheck fails (e.g. circular import)
docker compose up -d --no-deps scheduler
docker compose ps scheduler
