#!/bin/bash
# Phase 1: Prepare Qwen3.6-27B Q8 + mmproj on the UIC host WITHOUT loading GPU.
# Safe to run while qwen2.5vl:32b is active in Ollama.
set -euo pipefail

MODEL_DIR="/opt/models/qwen3.6-27b"
LLAMA_BIN="/opt/llama.cpp/bin/llama-server"
SERVICE_NAME="qwen36-llama-server.service"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Phase 1: prepare Qwen3.6-27B Q8 (no GPU load) ==="

mkdir -p "$MODEL_DIR" /opt/llama.cpp-cuda /opt/llama.cpp/bin

if [ ! -x /opt/llama.cpp-cuda/llama-server ]; then
  echo "Installing CUDA llama.cpp binaries..."
  tmp="/tmp/llama-cuda.tar.gz"
  curl -L -o "$tmp" "https://github.com/ai-dock/llama.cpp-cuda/releases/download/b10216/llama.cpp-b10216-cuda-12.8-amd64.tar.gz"
  tar -xzf "$tmp" -C /opt/llama.cpp-cuda --strip-components=1 2>/dev/null || tar -xzf "$tmp" -C /opt/llama.cpp-cuda
  apt-get install -y -qq libnccl2 >/dev/null 2>&1 || true
fi
ln -sf /opt/llama.cpp-cuda/llama-server "$LLAMA_BIN"

if [ ! -f "$MODEL_DIR/Qwen3.6-27B-Q8_0.gguf" ] || [ ! -f "$MODEL_DIR/mmproj-Qwen3.6-27B-Q8_0.gguf" ]; then
  echo "Downloading GGUF weights (~29GB)..."
  if [ ! -d /opt/hf-venv ]; then
    python3 -m venv /opt/hf-venv
    /opt/hf-venv/bin/pip install -q huggingface_hub hf_transfer
  fi
  HF_HUB_ENABLE_HF_TRANSFER=1 /opt/hf-venv/bin/python <<'PY'
import os
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
from huggingface_hub import hf_hub_download

repo = "ggml-org/Qwen3.6-27B-GGUF"
dest = "/opt/models/qwen3.6-27b"
for name in ("Qwen3.6-27B-Q8_0.gguf", "mmproj-Qwen3.6-27B-Q8_0.gguf"):
    print(f"Fetching {name}...")
    hf_hub_download(repo_id=repo, filename=name, local_dir=dest)
PY
else
  echo "Model files already present; skipping download."
fi

ls -lh "$MODEL_DIR"/

echo "Installing systemd unit (disabled until cutover)..."
cp "$REPO_ROOT/deploy/qwen36-llama-server.service" "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
systemctl disable "$SERVICE_NAME" 2>/dev/null || true
systemctl stop "$SERVICE_NAME" 2>/dev/null || true

echo ""
echo "Phase 1 complete. GPU was NOT loaded."
echo "  Models: $MODEL_DIR"
echo "  Binary: $LLAMA_BIN"
echo "  Service: $SERVICE_NAME (disabled/stopped)"
echo ""
echo "When qwen2.5vl:32b work is finished, run:"
echo "  bash $REPO_ROOT/deploy/cutover-qwen36-llama.sh"
