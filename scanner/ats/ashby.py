"""Ashby job board adapter."""

from __future__ import annotations

from scanner.http import fetch_json
from scanner.records import make_job
from scanner.text import strip_html

BASE = "https://api.ashbyhq.com/posting-api/job-board"


def _compensation(job: dict) -> str:
    compensation = job.get("compensation")

    if not isinstance(compensation, dict):
        return ""

    summary = compensation.get("compensationTierSummary")

    return str(summary or "").strip()


def fetch(company: dict) -> list[dict]:
    slug = company["slug"]

    payload = fetch_json(
        f"{BASE}/{slug}",
        params={"includeCompensation": "true"},
    )

    jobs = payload.get("jobs") if isinstance(payload, dict) else None

    if not isinstance(jobs, list):
        return []

    records = []

    for job in jobs:
        if not isinstance(job, dict):
            continue

        # isListed false means the posting is hidden on the public board.
        if job.get("isListed") is False:
            continue

        job_id = job.get("id")

        if job_id is None:
            continue

        description = job.get("descriptionPlain") or strip_html(
            job.get("descriptionHtml")
        )

        records.append(
            make_job(
                ats="ashby",
                company=company["name"],
                company_slug=slug,
                job_id=job_id,
                title=str(job.get("title") or "").strip(),
                url=str(job.get("jobUrl") or ""),
                location=str(job.get("location") or "").strip(),
                team=str(job.get("team") or job.get("department") or "").strip(),
                posted_at=job.get("publishedAt") or job.get("updatedAt"),
                description=str(description or ""),
                salary_context=_compensation(job),
            )
        )

    return records
