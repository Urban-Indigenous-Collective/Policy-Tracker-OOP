#!/bin/bash
# Detect (and optionally remove) stale Windows netsh portproxy rules that break
# the Policy Tracker LLM under WSL2 networkingMode=mirrored.
#
# Incident: static portproxy 0.0.0.0:8080 → old WSL NAT IP occupied :8080 on
# Windows while mirrored networking no longer uses that NAT address. llama-server
# could not bind → crash loop; discovery looked "quiet" with 0 analyzed.
#
# Rule: with mirrored networking, bind llama-server / Ollama in WSL on 0.0.0.0
# and do NOT portproxy LLM ports to ephemeral WSL NAT IPs. Mirrored mode +
# localhostForwarding expose WSL listeners on the Windows host / Tailscale IP.
#
# Run inside WSL on the UIC host:
#   bash deploy/fix-llm-portproxy.sh            # check only (exit 1 if stale)
#   bash deploy/fix-llm-portproxy.sh --fix     # delete stale 8080 (+11434)
#   bash deploy/fix-llm-portproxy.sh --fix --also-3478
#   bash deploy/fix-llm-portproxy.sh --fix --check-models
#
# From a Mac (Windows OpenSSH mangles pipes/redirs; avoid `bash -s < file` — it can
# truncate). Prefer a path inside WSL after CD, or nest a heredoc that writes /tmp:
#   ssh uic-server "wsl -d Ubuntu -- bash /opt/policy-tracker/deploy/fix-llm-portproxy.sh --fix"
set -euo pipefail

NETSH="${NETSH:-/mnt/c/Windows/System32/netsh.exe}"
LLM_PORTS="${LLM_PORTS:-8080 11434}"
# 3478 is often TURN/Jitsi — only touch with --also-3478
OPTIONAL_PORTS=""
DO_FIX=0
CHECK_MODELS=0
RESTART_LLAMA=0

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --fix) DO_FIX=1 ;;
    --check) DO_FIX=0 ;;
    --check-models) CHECK_MODELS=1 ;;
    --restart-llama) RESTART_LLAMA=1 ;;
    --also-3478) OPTIONAL_PORTS="3478" ;;
    -h|--help) usage 0 ;;
    *)
      echo "Unknown arg: $1" >&2
      usage 1
      ;;
  esac
  shift
done

if [ ! -x "$NETSH" ]; then
  echo "FAIL: netsh.exe not found at $NETSH (run on WSL with /mnt/c mounted)" >&2
  exit 2
fi

wsl_ipv4s() {
  ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | sort -u
}

# Returns connect addresses that are NOT present on this WSL instance.
# 127.0.0.1 / ::1 are treated as intentional loopback forwards (not NAT-stale).
is_stale_connect() {
  local addr="$1"
  case "$addr" in
    127.0.0.1|::1|localhost) return 1 ;;
  esac
  if echo "$WSL_IPS" | grep -qxF "$addr"; then
    return 1
  fi
  return 0
}

parse_portproxy() {
  # Emit: listen_addr listen_port connect_addr connect_port
  # Strip CR from Windows netsh output so port fields match /^[0-9]+$/.
  "$NETSH" interface portproxy show all 2>/dev/null | tr -d '\r' | awk '
    /^[0-9.*]+/ || $1 ~ /^\[/ {
      # netsh columns: Address Port Address Port (IPv4 table)
      if (NF >= 4 && $2 ~ /^[0-9]+$/ && $4 ~ /^[0-9]+$/) {
        print $1, $2, $3, $4
      }
    }
  '
}

delete_v4_proxy() {
  local listen_addr="$1" listen_port="$2"
  echo "Deleting portproxy ${listen_addr}:${listen_port} ..."
  "$NETSH" interface portproxy delete v4tov4 \
    listenaddress="$listen_addr" listenport="$listen_port"
}

WSL_IPS="$(wsl_ipv4s)"
echo "=== WSL IPv4 addresses ==="
echo "$WSL_IPS" | sed 's/^/  /'
echo ""
echo "=== Windows portproxy (netsh) ==="
"$NETSH" interface portproxy show all || true
echo ""

TARGET_PORTS="$LLM_PORTS $OPTIONAL_PORTS"
stale_count=0
deleted_count=0
STALE_LINES=()

# mapfile avoids `set -e` aborting on the final failed `read` EOF.
mapfile -t PP_LINES < <(parse_portproxy || true)
for line in "${PP_LINES[@]+"${PP_LINES[@]}"}"; do
  [ -n "${line:-}" ] || continue
  # shellcheck disable=SC2086
  set -- $line
  laddr="${1:-}" lport="${2:-}" caddr="${3:-}" cport="${4:-}"
  [ -n "$lport" ] || continue
  interest=0
  for p in $TARGET_PORTS; do
    if [ "$lport" = "$p" ]; then
      interest=1
      break
    fi
  done
  [ "$interest" -eq 1 ] || continue

  if is_stale_connect "$caddr"; then
    echo "STALE  ${laddr}:${lport} → ${caddr}:${cport} (connectaddress not on this WSL)"
    STALE_LINES+=("$laddr $lport $caddr $cport")
    stale_count=$((stale_count + 1))
  else
    # Under mirrored networking, any static LLM portproxy is discouraged even if
    # the connectaddress currently matches — NAT IPs change across WSL boots.
    if [ -f /mnt/c/Users/info/.wslconfig ] \
      && grep -qiE '^\s*networkingMode\s*=\s*mirrored' /mnt/c/Users/info/.wslconfig 2>/dev/null; then
      echo "WARN   ${laddr}:${lport} → ${caddr}:${cport} (mirrored mode: prefer no LLM portproxy; bind in WSL)"
    else
      echo "OK     ${laddr}:${lport} → ${caddr}:${cport}"
    fi
  fi
done

if [ "$stale_count" -eq 0 ]; then
  echo ""
  echo "No stale LLM portproxy rules for ports: $TARGET_PORTS"
else
  echo ""
  echo "Found $stale_count stale LLM-related portproxy rule(s)."
  if [ "$DO_FIX" -eq 1 ]; then
    for line in "${STALE_LINES[@]}"; do
      # shellcheck disable=SC2086
      set -- $line
      delete_v4_proxy "$1" "$2"
      deleted_count=$((deleted_count + 1))
    done
    echo "Deleted $deleted_count rule(s). Current portproxy:"
    "$NETSH" interface portproxy show all || true
  else
    echo "Re-run with --fix to delete stale 8080/11434 proxies (add --also-3478 only if sure)."
  fi
fi

echo ""
echo "=== llama-server / :8080 ==="
llama_active=0
if systemctl is-active --quiet qwen36-llama-server.service 2>/dev/null; then
  echo "OK  qwen36-llama-server.service is active"
  llama_active=1
else
  echo "WARN qwen36-llama-server.service is not active"
fi

if ss -tlnp 2>/dev/null | grep -qE '[:.]8080\s'; then
  echo "OK  something is listening on :8080 in WSL"
  ss -tlnp 2>/dev/null | grep -E '[:.]8080\s' || true
else
  echo "WARN nothing listening on :8080 in WSL"
  if [ "$RESTART_LLAMA" -eq 1 ] || [ "$DO_FIX" -eq 1 ]; then
    if systemctl list-unit-files qwen36-llama-server.service >/dev/null 2>&1; then
      echo "Attempting systemctl restart qwen36-llama-server.service ..."
      systemctl restart qwen36-llama-server.service || true
      sleep 3
      if systemctl is-active --quiet qwen36-llama-server.service; then
        echo "OK  service restarted"
        llama_active=1
      else
        echo "FAIL service still down after restart" >&2
        journalctl -u qwen36-llama-server.service -n 30 --no-pager || true
      fi
    fi
  fi
fi

# Windows-side :8080 held by portproxy while llama down is the original failure mode.
win_8080_proxy=0
mapfile -t PP_LINES2 < <(parse_portproxy || true)
for line in "${PP_LINES2[@]+"${PP_LINES2[@]}"}"; do
  [ -n "${line:-}" ] || continue
  # shellcheck disable=SC2086
  set -- $line
  laddr="${1:-}" lport="${2:-}" caddr="${3:-}" cport="${4:-}"
  [ "$lport" = "8080" ] || continue
  win_8080_proxy=1
  echo "WARN Windows portproxy still owns listen ${laddr}:8080 → ${caddr}:${cport}"
done

if [ "$win_8080_proxy" -eq 1 ] && [ "$llama_active" -eq 0 ]; then
  echo "FAIL :8080 held by Windows portproxy while llama-server is down (classic stale-NAT failure)" >&2
  if [ "$DO_FIX" -eq 0 ]; then
    exit 1
  fi
fi

if [ "$CHECK_MODELS" -eq 1 ]; then
  echo ""
  echo "=== GET /v1/models ==="
  if curl -sf --max-time 15 http://127.0.0.1:8080/v1/models >/dev/null; then
    echo "OK  http://127.0.0.1:8080/v1/models"
  else
    echo "FAIL http://127.0.0.1:8080/v1/models" >&2
    exit 1
  fi
fi

if [ "$stale_count" -gt 0 ] && [ "$DO_FIX" -eq 0 ]; then
  exit 1
fi

echo ""
echo "Done."
exit 0
