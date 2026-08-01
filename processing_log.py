import threading
from collections import deque

_lock = threading.Lock()
_log: deque[str] = deque(maxlen=200)
_phase = "Idle"
_detail = ""

PHASE_LABELS = {
    "Idle": "Idle",
    "fetch": "Fetching document",
    "metadata": "Loading bill metadata",
    "analysis": "Running UIC analysis (LLM)",
    "pros_cons": "Generating pros and cons (LLM)",
    "complete": "Finishing up",
    "batch": "Processing batch",
}


def reset():
    global _phase, _detail
    with _lock:
        _log.clear()
        _phase = "Idle"
        _detail = ""


def log(message: str):
    with _lock:
        _log.append(message)


def set_phase(phase: str, detail: str = ""):
    global _phase, _detail
    with _lock:
        _phase = phase
        _detail = detail
    label = PHASE_LABELS.get(phase, phase)
    if detail:
        log(f"{label}: {detail}")
    else:
        log(label)


def snapshot() -> dict:
    with _lock:
        return {
            "lines": list(_log),
            "phase": _phase,
            "phase_label": PHASE_LABELS.get(_phase, _phase),
            "detail": _detail,
        }
