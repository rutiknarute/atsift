"""Greenhouse job board adapter."""

from __future__ import annotations

from scanner.http import fetch_json
from scanner.records import make_job
from scanner.text import department_names, location_name, strip_html

BASE = "https://boards-api.greenhouse.io/v1/boards"


def fetch(company: dict) -> list[dict]:
    slug = company["slug"]

    # content=true returns the description inline, which avoids a second
    # request per posting.
    payload = fetch_json(f"{BASE}/{slug}/jobs", params={"content": "true"})

    jobs = payload.get("jobs") if isinstance(payload, dict) else None

    if not isinstance(jobs, list):
        return []

    records = []

    for job in jobs:
        if not isinstance(job, dict):
            continue

        job_id = job.get("id")

        if job_id is None:
            continue

        records.append(
            make_job(
                ats="greenhouse",
                company=company["name"],
                company_slug=slug,
                job_id=job_id,
                title=str(job.get("title") or "").strip(),
                url=str(job.get("absolute_url") or ""),
                location=location_name(job.get("location")),
                team=department_names(job.get("departments")),
                posted_at=job.get("updated_at") or job.get("created_at"),
                description=strip_html(job.get("content")),
            )
        )

    return records
