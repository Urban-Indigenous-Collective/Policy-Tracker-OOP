#!/usr/bin/env python3
"""Live backfill progress viewer — polls discovery_progress.json in the run container."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time

PROGRESS_RE = re.compile(
    r"PROGRESS phase=(\w+) step=(\d+)/(\d+) pct=(\d+) "
    r"discovered=(\d+) analyzed=(\d+) rejected=(\d+) skipped=(\d+) errors=(\d+) detail='(.*)'"
)


def render_bar(current: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return f"[{'?' * width}]"
    current = max(0, min(current, total))
    filled = int(width * current / total)
    if filled >= width:
        return f"[{'=' * width}]"
    return f"[{'=' * filled}{'>' if filled < width else ''}{' ' * (width - filled - 1)}]"


def find_container() -> str:
    result = subprocess.run(
        ["docker", "ps", "-q", "--filter", "name=policy-tracker-scheduler-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return lines[0] if lines else ""


def docker_cat(container_id: str, path: str) -> str | None:
    result = subprocess.run(
        ["docker", "exec", container_id, "cat", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def read_progress(container_id: str) -> dict | None:
    raw = docker_cat(container_id, "/app/data/discovery_progress.json")
    if not raw or not raw.strip():
        return None
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        return None
    total = int(state.get("step_total") or 0)
    cur = int(state.get("step_current") or 0)
    state["percent"] = int(100 * cur / total) if total else 0
    return state


def recent_logs(container_id: str, n: int = 4) -> list[str]:
    result = subprocess.run(
        ["docker", "logs", "--tail", str(n), container_id],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = (result.stdout or "") + (result.stderr or "")
    out: list[str] = []
    for line in lines.splitlines():
        line = line.strip()
        if line and "PROGRESS " not in line:
            out.append(line[-120:])
    return out[-n:]


def format_status(state: dict) -> str:
    cur = int(state.get("step_current") or 0)
    total = int(state.get("step_total") or 0)
    pct = int(state.get("percent") or 0)
    bar = render_bar(cur, total, width=28)
    detail = (state.get("detail") or "").strip()
    detail_bit = f" | {detail[:55]}" if detail else ""
    return (
        f"{bar} {pct:3d}% | {state.get('phase_label', '?')} ({cur}/{total}) | "
        f"found {state.get('discovered', 0)} | +{state.get('analyzed', 0)} pending | "
        f"{state.get('rejected', 0)} rej | {state.get('skipped', 0)} skip | "
        f"{state.get('errors', 0)} err{detail_bit}"
    )


def parse_log_fallback(container_id: str) -> dict | None:
    result = subprocess.run(
        ["docker", "logs", "--tail", "30", container_id],
        capture_output=True,
        text=True,
        check=False,
    )
    text = (result.stdout or "") + (result.stderr or "")
    for line in reversed(text.splitlines()):
        match = PROGRESS_RE.search(line)
        if match:
            phase, cur, total, pct, disc, anal, rej, skip, err, detail = match.groups()
            labels = {
                "initializing": "Initializing",
                "legiscan": "LegiScan search",
                "state_crawl": "State site crawl",
                "processing": "Analyzing candidates",
                "complete": "Complete",
            }
            return {
                "phase": phase,
                "phase_label": labels.get(phase, phase),
                "step_current": int(cur),
                "step_total": int(total),
                "percent": int(pct),
                "discovered": int(disc),
                "analyzed": int(anal),
                "rejected": int(rej),
                "skipped": int(skip),
                "errors": int(err),
                "detail": detail,
            }
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch backfill with progress bar")
    parser.add_argument("--container", help="Docker container id (auto-detect if omitted)")
    parser.add_argument("--plain", action="store_true", help="Stream raw logs only")
    parser.add_argument("--interval", type=float, default=2.0, help="Refresh seconds")
    args = parser.parse_args()

    cid = args.container or find_container()
    if not cid:
        print("No active policy-tracker-scheduler-run container.", file=sys.stderr)
        sys.exit(1)

    if args.plain:
        subprocess.call(["docker", "logs", "-f", "--tail", "50", cid])
        return

    print(f"Watching container {cid[:12]}… (Ctrl+C to stop)\n")
    last_phase = ""

    try:
        while True:
            state = read_progress(cid) or parse_log_fallback(cid)
            running = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", cid],
                capture_output=True,
                text=True,
                check=False,
            )
            is_running = (running.stdout or "").strip() == "true"

            if state:
                line = format_status(state)
                if state.get("phase") != last_phase:
                    if last_phase:
                        print()
                    last_phase = str(state.get("phase"))
                sys.stdout.write("\033[2K\r" + line)
                sys.stdout.flush()
                for log_line in recent_logs(cid, 3):
                    if log_line not in line:
                        pass  # keep bar on one line; logs on phase change only
                if state.get("phase") == "complete" and not is_running:
                    print("\n\nBackfill pass complete.")
                    break
            else:
                sys.stdout.write("\033[2K\rWaiting for progress data…")
                sys.stdout.flush()

            if not is_running:
                final = read_progress(cid) or parse_log_fallback(cid)
                if final:
                    print("\n" + format_status(final))
                for log_line in recent_logs(cid, 6):
                    print(f"  {log_line}")
                print("\nContainer stopped.")
                break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
