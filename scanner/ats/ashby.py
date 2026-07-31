"""Ashby job board adapter."""

from __future__ import annotations

import json

from scanner.http import fetch_json
from scanner.records import make_job
from scanner.text import strip_html

BASE = "https://api.ashbyhq.com/posting-api/job-board"


def _compensation(job: dict) -> str:
    compensation = job.get("compensation")

    if not isinstance(compensation, dict):
        return ""

    summary = compensation.get("compensationTierSummary")

    if summary:
        return str(summary).strip()

    return json.dumps(compensation, ensure_ascii=False)


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

        location = str(job.get("location") or "").strip()
        is_remote = (
            bool(job.get("isRemote"))
            or str(job.get("workplaceType") or "").casefold() == "remote"
        )

        if is_remote and "remote" not in location.casefold():
            location = f"{location} · Remote" if location else "Remote"

        records.append(
            make_job(
                ats="ashby",
                company=company["name"],
                company_slug=slug,
                job_id=job_id,
                title=str(job.get("title") or "").strip(),
                url=str(job.get("applyUrl") or job.get("jobUrl") or ""),
                location=location,
                team=str(job.get("team") or job.get("department") or "").strip(),
                posted_at=job.get("publishedAt") or job.get("updatedAt"),
                description=str(description or ""),
                salary_context=_compensation(job),
            )
        )

    return records
