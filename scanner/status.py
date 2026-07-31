"""
Live scan progress and cancellation.

A sweep takes real time, so the UI polls this. State is held in memory (the
API and the scan thread share one process) and mirrored to disk so a restart
does not leave the UI claiming a scan is still running.
"""

from __future__ import annotations

import threading

from scanner.config import SCAN_STATUS_PATH
from scanner.dates import iso
from scanner.jsonio import read_json, write_json

_lock = threading.Lock()

cancel_event = threading.Event()

_IDLE = {
    "state": "idle",
    "phase": "",
    "message": "",
    "companies_done": 0,
    "companies_total": 0,
    "jobs_found": 0,
    "matches": 0,
    "analyzed": 0,
    "analyzed_total": 0,
    "lookback_hours": None,
    "dataset": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}

_status: dict = dict(_IDLE)


def _persist() -> None:
    try:
        write_json(SCAN_STATUS_PATH, _status)
    except OSError:
        # Progress is a convenience; never fail a scan over a status write.
        pass


def reset() -> None:
    with _lock:
        _status.clear()
        _status.update(_IDLE)
        _persist()


def start(*, lookback_hours: float, dataset: str, companies_total: int) -> None:
    cancel_event.clear()

    with _lock:
        _status.clear()
        _status.update(_IDLE)
        _status.update(
            {
                "state": "running",
                "phase": "scanning",
                "message": "Reading boards and screening roles as they come in…",
                "companies_total": companies_total,
                "lookback_hours": lookback_hours,
                "dataset": dataset,
                "started_at": iso(),
            }
        )
        _persist()


def update(**fields) -> None:
    with _lock:
        _status.update(fields)
        _persist()


def bump(field: str, amount: int = 1) -> None:
    with _lock:
        _status[field] = int(_status.get(field) or 0) + amount

        # Persisting on every company would hammer the disk; the API reads
        # the in-memory copy anyway.
        if field == "companies_done" and _status[field] % 25 == 0:
            _persist()


def finish(*, message: str = "Scan complete.", error: str | None = None) -> None:
    with _lock:
        _status.update(
            {
                "state": "error" if error else "done",
                "phase": "",
                "message": message,
                "finished_at": iso(),
                "error": error,
            }
        )
        _persist()


def cancelled() -> bool:
    return cancel_event.is_set()


def request_cancel() -> None:
    cancel_event.set()

    with _lock:
        _status.update(
            {
                "phase": "cancelling",
                "message": "Stopping the scan…",
            }
        )
        _persist()


def snapshot() -> dict:
    with _lock:
        return dict(_status)


def is_running() -> bool:
    with _lock:
        return _status.get("state") == "running"


def load_persisted() -> None:
    """
    On boot, adopt the last status but never inherit a 'running' state — the
    thread that owned it died with the previous process.
    """

    stored = read_json(SCAN_STATUS_PATH, None)

    if not isinstance(stored, dict):
        return

    if stored.get("state") == "running":
        stored["state"] = "idle"
        stored["message"] = "Previous scan did not finish."

    with _lock:
        _status.clear()
        _status.update({**_IDLE, **stored})
