"""Workable job board adapter."""

from __future__ import annotations

from scanner.http import fetch_json
from scanner.records import make_job
from scanner.text import strip_html

BASE = "https://www.workable.com/api/accounts"


def _location(job: dict) -> str:
    """
    Build a location string from Workable's flat fields.

    Note `state` here is the region ("District of Columbia"), not a publish
    status — the two are easy to confuse and the account endpoint only ever
    returns published jobs anyway.
    """

    parts = [
        str(job.get("city") or "").strip(),
        str(job.get("state") or "").strip(),
        str(job.get("country") or "").strip(),
    ]

    # Fall back to the structured list when the flat fields are blank.
    if not any(parts):
        locations = job.get("locations")

        if isinstance(locations, list) and locations:
            first = locations[0] if isinstance(locations[0], dict) else {}
            parts = [
                str(first.get("city") or "").strip(),
                str(first.get("region") or "").strip(),
                str(first.get("country") or "").strip(),
            ]

    text = ", ".join(part for part in parts if part)

    if job.get("telecommuting"):
        text = f"Remote — {text}" if text else "Remote"

    return text


def fetch(company: dict) -> list[dict]:
    slug = company["slug"]

    payload = fetch_json(f"{BASE}/{slug}", params={"details": "true"})

    jobs = payload.get("jobs") if isinstance(payload, dict) else None

    if not isinstance(jobs, list):
        return []

    records = []

    for job in jobs:
        if not isinstance(job, dict):
            continue

        shortcode = job.get("shortcode") or job.get("id")

        if not shortcode:
            continue

        records.append(
            make_job(
                ats="workable",
                company=company["name"],
                company_slug=slug,
                job_id=shortcode,
                title=str(job.get("title") or "").strip(),
                url=str(
                    job.get("url")
                    or job.get("application_url")
                    or f"https://apply.workable.com/{slug}/j/{shortcode}/"
                ),
                location=_location(job),
                team=str(job.get("department") or "").strip(),
                posted_at=job.get("published_on")
                or job.get("created_at")
                or job.get("published"),
                description=strip_html(
                    job.get("description") or job.get("full_description")
                ),
            )
        )

    return records
