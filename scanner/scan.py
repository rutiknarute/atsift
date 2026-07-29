"""
The sweep.

Order matters, and it is all about cost. Each stage is far more expensive than
the one before it, so each one only ever sees what survived the last:

    fetch board  →  boolean search  →  time window  →  location  →  LLM

The chosen timeframe is applied here, at the source — not as a filter over
results afterwards. The window the user picked and the window the results were
drawn from are the same window, always.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from scanner import status
from scanner.analysis import get_job_analysis
from scanner.ats import fetch_company, needs_detail_fetch
from scanner.ats import fetch_description
from scanner.boolean_search import ALL_CATEGORIES, title_categories
from scanner.companies import load_companies, resolve_dataset
from scanner.config import (
    DEFAULT_LOOKBACK_HOURS,
    MAX_ANALYSIS_PER_SCAN,
    MAX_LOOKBACK_HOURS,
    MAX_WORKERS,
    USE_OLLAMA_ANALYSIS,
)
from scanner.dates import within_window
from scanner.http import BoardUnavailable
from scanner.locations import screen_location
from scanner.records import dedupe_jobs
from scanner.store import (
    load_analysis_cache,
    save_analysis_cache,
    save_jobs,
)

_scan_lock = threading.Lock()
_scan_thread: threading.Thread | None = None


def clamp_lookback(value) -> float:
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return float(DEFAULT_LOOKBACK_HOURS)

    if hours <= 0:
        return float(DEFAULT_LOOKBACK_HOURS)

    return float(min(hours, MAX_LOOKBACK_HOURS))


def _scan_company(company: dict, lookback_hours: float, categories: list[str]):
    """Fetch one board and keep only what passes search + window."""

    try:
        jobs = fetch_company(company)
    except BoardUnavailable:
        return []
    except Exception:
        # One malformed board must never take down the sweep.
        return []

    kept = []

    for job in jobs:
        matched = title_categories(job.get("title"), categories)

        if not matched:
            continue

        if not within_window(job.get("posted_at"), lookback_hours):
            continue

        job["categories"] = matched
        kept.append(job)

    return kept


def run_scan(
    *,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    dataset: str = "main",
    categories: list[str] | None = None,
) -> dict:
    """Run one full sweep. Returns the result summary."""

    lookback_hours = clamp_lookback(lookback_hours)
    dataset = resolve_dataset(dataset)
    wanted = [c for c in (categories or ALL_CATEGORIES) if c in ALL_CATEGORIES]
    wanted = wanted or list(ALL_CATEGORIES)

    companies = load_companies(dataset)

    status.start(
        lookback_hours=lookback_hours,
        dataset=dataset,
        companies_total=len(companies),
    )

    matches: list[dict] = []

    try:
        # --- Stage 1: sweep every board concurrently --------------------
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_scan_company, company, lookback_hours, wanted): company
                for company in companies
            }

            for future in as_completed(futures):
                if status.cancelled():
                    for pending in futures:
                        pending.cancel()
                    break

                status.bump("companies_done")

                try:
                    found = future.result()
                except Exception:
                    found = []

                if found:
                    matches.extend(found)
                    status.update(jobs_found=len(matches))

        if status.cancelled():
            status.finish(message="Scan cancelled.")
            return _summary(matches, lookback_hours, dataset, cancelled=True)

        matches = dedupe_jobs(matches)

        # --- Stage 2: location screen (free, pattern-based) -------------
        status.update(
            phase="screening",
            message="Screening locations…",
            matches=len(matches),
        )

        screened = []

        for job in matches:
            verdict = screen_location(job.get("location"))

            if verdict == "NON_US":
                continue

            job["location_verdict"] = verdict
            screened.append(job)

        matches = screened
        status.update(matches=len(matches))

        # --- Stage 3: descriptions, only for survivors ------------------
        pending_detail = [
            job
            for job in matches
            if needs_detail_fetch(job.get("ats")) and not job.get("description")
        ]

        if pending_detail and not status.cancelled():
            status.update(
                phase="descriptions",
                message="Fetching job descriptions…",
            )

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures = {
                    pool.submit(fetch_description, job): job
                    for job in pending_detail
                }

                for future in as_completed(futures):
                    if status.cancelled():
                        break

                    job = futures[future]

                    try:
                        job["description"] = future.result() or ""
                    except Exception:
                        job["description"] = ""

        # --- Stage 4: LLM analysis, the expensive one -------------------
        analyzable = [job for job in matches if job.get("description")]
        analyzable = analyzable[:MAX_ANALYSIS_PER_SCAN]

        if USE_OLLAMA_ANALYSIS and analyzable and not status.cancelled():
            status.update(
                phase="analyzing",
                message="Screening postings with the local model…",
                analyzed_total=len(analyzable),
            )

            cache = load_analysis_cache()

            for job in analyzable:
                if status.cancelled():
                    break

                job["analysis"] = get_job_analysis(job, cache)
                status.bump("analyzed")

            save_analysis_cache(cache)

        # Drop anything the model positively identified as non-US.
        matches = [
            job
            for job in matches
            if (job.get("analysis") or {}).get("us_location_eligible") != "NO"
        ]

        matches.sort(key=lambda job: job.get("age_hours") or 1e9)

        save_jobs(matches, lookback_hours=lookback_hours, dataset=dataset)

        status.update(matches=len(matches))
        status.finish(
            message=(
                "Scan cancelled."
                if status.cancelled()
                else f"Found {len(matches)} matching roles."
            )
        )

        return _summary(matches, lookback_hours, dataset)

    except Exception as error:
        status.finish(message="Scan failed.", error=str(error))
        raise


def _summary(jobs, lookback_hours, dataset, *, cancelled: bool = False) -> dict:
    return {
        "count": len(jobs),
        "lookback_hours": lookback_hours,
        "dataset": dataset,
        "cancelled": cancelled,
    }


def start_scan_thread(**kwargs) -> bool:
    """Start a scan in the background. False when one is already running."""

    global _scan_thread

    with _scan_lock:
        if _scan_thread is not None and _scan_thread.is_alive():
            return False

        # Mark it running here, synchronously. The caller gets the status back
        # in the same response, and a UI that polls immediately never sees a
        # stale "idle" for a scan that has in fact started.
        status.update(
            state="running",
            phase="starting",
            message="Starting scan…",
            error=None,
            finished_at=None,
        )

        def target():
            try:
                run_scan(**kwargs)
            except Exception:
                pass

        _scan_thread = threading.Thread(
            target=target,
            name="scan",
            daemon=True,
        )
        _scan_thread.start()

        return True
