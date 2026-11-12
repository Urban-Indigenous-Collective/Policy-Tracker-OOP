#!/bin/bash
# Verify Phase 1 prep for Qwen3.6 cutover is complete on the host.
# Also fails when Windows portproxy points LLM ports at a dead WSL NAT IP
# (mirrored-networking hazard — see deploy/fix-llm-portproxy.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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

echo "=== Mirrored networking / portproxy (LLM) ==="
# Always run: stale 0.0.0.0:8080 → old NAT IP blocks llama-server bind.
if [ -x "$ROOT/deploy/fix-llm-portproxy.sh" ]; then
  if bash "$ROOT/deploy/fix-llm-portproxy.sh" --check; then
    echo "OK  LLM portproxy check"
    ok=$((ok + 1))
  else
    echo "FAIL LLM portproxy check (stale NAT target or :8080 held while llama down)"
    echo "     Fix: bash $ROOT/deploy/fix-llm-portproxy.sh --fix --check-models"
    fail=$((fail + 1))
  fi
else
  echo "FAIL deploy/fix-llm-portproxy.sh missing"
  fail=$((fail + 1))
fi

# Extra explicit signal when Windows still proxies :8080 and nothing in WSL listens.
NETSH="${NETSH:-/mnt/c/Windows/System32/netsh.exe}"
if [ -x "$NETSH" ]; then
  if "$NETSH" interface portproxy show all 2>/dev/null | tr -d '\r' | awk '$2=="8080"{found=1} END{exit !found}'; then
    if ! ss -tlnp 2>/dev/null | grep -qE '[:.]8080\s'; then
      echo "FAIL Windows portproxy owns :8080 but nothing listens in WSL (llama cannot bind)"
      fail=$((fail + 1))
    fi
  fi
fi

echo ""
echo "=== Phase 1 prep ==="
check "main GGUF" "[ -f /opt/models/qwen3.6-27b/Qwen3.6-27B-Q8_0.gguf ]"
check "mmproj GGUF" "[ -f /opt/models/qwen3.6-27b/mmproj-Qwen3.6-27B-Q8_0.gguf ]"
check "llama-server binary" "[ -x /opt/llama.cpp/bin/llama-server ] || [ -L /opt/llama.cpp/bin/llama-server ]"
check "systemd unit installed" "[ -f /etc/systemd/system/qwen36-llama-server.service ]"

# After cutover the service is active; treat that as OK for readiness of the stack.
if systemctl is-active --quiet qwen36-llama-server.service 2>/dev/null; then
  echo "OK  qwen36-llama-server.service active (post-cutover)"
  ok=$((ok + 1))
  check "port 8080 listening" "ss -tlnp 2>/dev/null | grep -qE '[:.]8080\s'"
else
  check "service disabled (not loaded)" "! systemctl is-active --quiet qwen36-llama-server.service"
  check "port 8080 free in WSL" "! ss -tlnp 2>/dev/null | grep -qE '[:.]8080\s'"
fi

echo ""
echo "Ollama status (legacy :11434 — optional after Qwen3.6 cutover):"
ollama ps 2>/dev/null || echo "(ollama unavailable)"

echo ""
if [ "$fail" -eq 0 ]; then
  echo "Checks passed ($ok ok)."
  if ! systemctl is-active --quiet qwen36-llama-server.service 2>/dev/null; then
    echo "Phase 1 ready. When qwen2.5vl work is done, run:"
    echo "  bash /opt/policy-tracker/deploy/cutover-qwen36-llama.sh"
  fi
  exit 0
fi
echo "$fail check(s) failed."
exit 1
