#!/bin/bash
# Phase 2: Cut production LLM from qwen2.5vl:32b (Ollama) to Qwen3.6-27B Q8 (llama-server).
# ONLY run when the current 2.5 job is finished and ollama ps is idle or safe to unload.
set -euo pipefail

WSL_DEPLOY_PATH="${WSL_DEPLOY_PATH:-/opt/policy-tracker}"
SERVICE_NAME="qwen36-llama-server.service"
ENV_FILE="$WSL_DEPLOY_PATH/.env"
SNIPPET="$(cd "$(dirname "$0")/.." && pwd)/deploy/llm-cutover.env.snippet"

echo "=== Phase 2: cut over to Qwen3.6-27B Q8 ==="

echo "Current Ollama status:"
ollama ps || true

read -r -p "Confirm qwen2.5vl:32b work is done and safe to unload? [y/N] " ans
if [[ "${ans,,}" != "y" ]]; then
  echo "Aborted."
  exit 1
fi

echo "Unloading qwen2.5vl:32b from Ollama..."
ollama stop qwen2.5vl:32b 2>/dev/null || true

echo "Starting llama-server..."
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"
sleep 5
systemctl is-active --quiet "$SERVICE_NAME"

echo "Smoke test (text JSON)..."
curl -sf http://127.0.0.1:8080/v1/models >/dev/null || { echo "llama-server /v1/models failed"; exit 1; }

if [ -f "$ENV_FILE" ]; then
  echo "Updating production .env LLM settings..."
  tmp="$(mktemp)"
  grep -v -E '^(LLM_BASE_URL|LLM_MODEL|LLM_REASONING|OLLAMA_BASE_URL|OLLAMA_MODEL)=' "$ENV_FILE" > "$tmp" || true
  cat "$SNIPPET" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
else
  echo "WARNING: $ENV_FILE not found; apply deploy/llm-cutover.env.snippet manually."
fi

echo "Restarting Docker services..."
cd "$WSL_DEPLOY_PATH"
docker compose restart web scheduler 2>/dev/null || docker compose up -d

echo ""
echo "Cutover complete."
echo "  llama-server: http://100.71.124.8:8080/v1"
echo "  Rollback: point .env back to Ollama :11434 and ollama run qwen2.5vl:32b"
