"""
The sweep.

Each posting is carried all the way through on its own:

    fetch board  →  boolean search  →  time window  →  location  →  JD  →  LLM

and is listed the moment it clears. Nothing waits for the whole catalog. The
order still matters for cost — each step only sees what survived the last — but
it is a pipeline per posting, not a phase across all of them, so the first
results land seconds into a scan instead of after every board has been read.

Boards are read by a worker pool while a single screening thread drains the
queue behind them: the local model can only look at one posting at a time, so
fetching and screening overlap rather than queue up.

The chosen timeframe is applied here, at the source — not as a filter over
results afterwards. The window the user picked and the window the results were
drawn from are the same window, always.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

from scanner import status
from scanner.analysis import fallback_analysis, get_job_analysis
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
from scanner.locations import job_has_confirmed_us_location, screen_location
from scanner.store import (
    load_analysis_cache,
    save_analysis_cache,
    save_jobs,
)

_scan_lock = threading.Lock()
_scan_thread: threading.Thread | None = None

# Screening runs one posting at a time. Publishing on this cadence lets the
# dashboard fill in as the model works, instead of rewriting the store for
# every single posting.
PUBLISH_EVERY_SECONDS = 3.0

_DONE = object()


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


def _prepare_company(
    company: dict,
    lookback_hours: float,
    categories: list[str],
) -> list[dict]:
    """
    One board, taken as far as it can go without the model.

    Location screening and the JD fetch happen here, inside the worker pool,
    so a posting reaches the screening queue ready to be read — and so the
    slow part of a board's work overlaps with every other board's.
    """

    ready = []

    for job in _scan_company(company, lookback_hours, categories):
        verdict = screen_location(job.get("location"))

        if verdict == "NON_US":
            continue

        job["location_verdict"] = verdict

        if needs_detail_fetch(job.get("ats")) and not job.get("description"):
            try:
                job["description"] = fetch_description(job) or ""
            except Exception:
                job["description"] = ""

        ready.append(job)

    return ready


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

    listed: list[dict] = []
    queue: Queue = Queue()
    listed_lock = threading.Lock()
    cache = load_analysis_cache()

    def screen_queued() -> None:
        """
        Read, screen and list one posting at a time.

        A single thread, because the local model is a single resource. It runs
        for the whole scan, so screening a posting overlaps with fetching the
        boards that come after it.
        """

        analyzed = 0
        published_at = 0.0

        while True:
            job = queue.get()

            if job is _DONE:
                return

            # On cancel, keep draining so the producer never blocks on a full
            # queue, but stop spending the model on work nobody asked for.
            if status.cancelled():
                continue

            if job.get("description"):
                budget_left = (
                    MAX_ANALYSIS_PER_SCAN <= 0
                    or analyzed < MAX_ANALYSIS_PER_SCAN
                )

                if USE_OLLAMA_ANALYSIS and budget_left:
                    try:
                        job["analysis"] = get_job_analysis(job, cache)
                    except Exception:
                        # A model failure still leaves a JD-backed record.
                        job["analysis"] = fallback_analysis(job)

                    analyzed += 1
                    status.bump("analyzed")
                else:
                    job["analysis"] = fallback_analysis(job)

            # A US-only product cannot list an unresolved location.
            if not job_has_confirmed_us_location(job):
                continue

            with listed_lock:
                listed.append(job)
                listed.sort(key=lambda item: item.get("age_hours") or 1e9)
                snapshot = list(listed)

            status.update(matches=len(snapshot))

            now = time.monotonic()

            if now - published_at >= PUBLISH_EVERY_SECONDS:
                published_at = now
                save_jobs(
                    snapshot,
                    lookback_hours=lookback_hours,
                    dataset=dataset,
                )

    screener = threading.Thread(
        target=screen_queued,
        daemon=True,
        name="job-screening",
    )
    screener.start()

    try:
        seen: set = set()

        try:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures = [
                    pool.submit(
                        _prepare_company,
                        company,
                        lookback_hours,
                        wanted,
                    )
                    for company in companies
                ]

                for future in as_completed(futures):
                    if status.cancelled():
                        for pending in futures:
                            pending.cancel()
                        break

                    status.bump("companies_done")

                    try:
                        found = future.result() or []
                    except Exception:
                        # One malformed board must never stop the sweep.
                        found = []

                    for job in found:
                        uid = job.get("uid")

                        if uid in seen:
                            continue

                        seen.add(uid)
                        status.bump("jobs_found")

                        if job.get("description"):
                            status.bump("analyzed_total")

                        queue.put(job)
        finally:
            # Always release the screening thread, even on cancel or failure,
            # and let it finish the postings already queued.
            queue.put(_DONE)
            screener.join()

        save_analysis_cache(cache)

        with listed_lock:
            final = _confirmed(list(listed))

        save_jobs(final, lookback_hours=lookback_hours, dataset=dataset)

        status.update(matches=len(final))
        cancelled = status.cancelled()
        status.finish(
            message=(
                f"Scan stopped. Kept {len(final)} confirmed roles."
                if cancelled
                else f"Found {len(final)} matching roles."
            )
        )

        return _summary(
            final,
            lookback_hours,
            dataset,
            cancelled=cancelled,
        )

    except Exception as error:
        status.finish(message="Scan failed.", error=str(error))
        raise


def _confirmed(
    matches: list[dict],
    *,
    pending: set | None = None,
) -> list[dict]:
    """
    The publishable view of a scan: analysed, US-confirmed, freshest first.

    ``pending`` holds the uids still queued for the model. Those are withheld
    rather than given a fallback record, so a posting appears once its own JD
    has actually been read — never as a placeholder that changes verdict a
    moment later.
    """

    queued = pending or set()
    ready = [
        job for job in matches if job.get("uid") not in queued
    ]

    # A provider or model failure still gets a deterministic JD-backed
    # manual-review record; successful LLM analyses remain untouched.
    for job in ready:
        if (
            job.get("description")
            and not isinstance(job.get("analysis"), dict)
        ):
            job["analysis"] = fallback_analysis(job)

    # A US-only product cannot return unresolved ambiguous locations.
    # Structured US locations survive without analysis; ambiguous ones
    # require an explicit YES from the model.
    confirmed = [
        job for job in ready if job_has_confirmed_us_location(job)
    ]
    confirmed.sort(key=lambda job: job.get("age_hours") or 1e9)

    return confirmed


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
