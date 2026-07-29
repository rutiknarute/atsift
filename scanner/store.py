"""The job store, the viewed-job set, and the analysis cache."""

from __future__ import annotations

import threading

from scanner.config import (
    ANALYSIS_CACHE_PATH,
    JOBS_STORE_PATH,
    VIEWED_JOBS_PATH,
)
from scanner.dates import iso
from scanner.jsonio import read_json, write_json

_lock = threading.Lock()


# --- Jobs -------------------------------------------------------------------


def load_jobs() -> dict:
    stored = read_json(JOBS_STORE_PATH, {})

    if not isinstance(stored, dict):
        return {"jobs": [], "scanned_at": None, "lookback_hours": None}

    stored.setdefault("jobs", [])
    stored.setdefault("scanned_at", None)
    stored.setdefault("lookback_hours", None)

    return stored


def save_jobs(jobs: list[dict], *, lookback_hours: float, dataset: str) -> None:
    with _lock:
        write_json(
            JOBS_STORE_PATH,
            {
                "jobs": jobs,
                "scanned_at": iso(),
                "lookback_hours": lookback_hours,
                "dataset": dataset,
                "count": len(jobs),
            },
        )


# --- Viewed -----------------------------------------------------------------


def load_viewed() -> set[str]:
    stored = read_json(VIEWED_JOBS_PATH, [])

    if isinstance(stored, dict):
        stored = stored.get("uids") or list(stored.keys())

    if not isinstance(stored, list):
        return set()

    return {str(uid) for uid in stored if uid}


def mark_viewed(uid: str) -> int:
    with _lock:
        viewed = load_viewed()
        viewed.add(str(uid))
        write_json(VIEWED_JOBS_PATH, sorted(viewed))

        return len(viewed)


# --- Analysis cache ---------------------------------------------------------


def load_analysis_cache() -> dict:
    stored = read_json(ANALYSIS_CACHE_PATH, {})

    return stored if isinstance(stored, dict) else {}


def save_analysis_cache(cache: dict) -> None:
    with _lock:
        write_json(ANALYSIS_CACHE_PATH, cache)
