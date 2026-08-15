#!/bin/bash
# Verify Phase 1 prep for Qwen3.6 cutover is complete on the host.
set -euo pipefail

ok=0
fail=0

check() {
  if eval "$2"; then
    echo "OK  $1"
    ok=$((ok + 1))
  else
    echo "FAIL $1"
    fail=$((fail + 1))
  fi
}

check "main GGUF" "[ -f /opt/models/qwen3.6-27b/Qwen3.6-27B-Q8_0.gguf ]"
check "mmproj GGUF" "[ -f /opt/models/qwen3.6-27b/mmproj-Qwen3.6-27B-Q8_0.gguf ]"
check "llama-server binary" "[ -x /opt/llama.cpp/bin/llama-server ] || [ -L /opt/llama.cpp/bin/llama-server ]"
check "systemd unit installed" "[ -f /etc/systemd/system/qwen36-llama-server.service ]"
check "service disabled (not loaded)" "! systemctl is-active --quiet qwen36-llama-server.service"
check "port 8080 free" "! ss -tlnp 2>/dev/null | grep -q ':8080 '"

echo ""
echo "Ollama status (should stay loaded until you cut over):"
ollama ps 2>/dev/null || echo "(ollama unavailable)"

echo ""
if [ "$fail" -eq 0 ]; then
  echo "Phase 1 ready. When qwen2.5vl work is done, run:"
  echo "  bash /opt/policy-tracker/deploy/cutover-qwen36-llama.sh"
  exit 0
fi
echo "$fail check(s) failed."
exit 1
