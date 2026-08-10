"""Rippling public job-board adapter."""

from __future__ import annotations

import json

from scanner.http import BoardUnavailable, fetch_json
from scanner.records import make_job
from scanner.text import strip_html

BASE = "https://ats.rippling.com/api/v2/board"
PAGE_SIZE = 1000
MAX_PAGES = 100


def _location(job: dict) -> str:
    values = []
    is_remote = False

    for location in job.get("locations") or []:
        if not isinstance(location, dict):
            continue

        name = str(location.get("name") or "").strip()

        if name:
            values.append(name)

        if str(location.get("workplaceType") or "").casefold() == "remote":
            is_remote = True

    text = " · ".join(dict.fromkeys(values))

    if is_remote and "remote" not in text.casefold():
        text = f"{text} · Remote" if text else "Remote"

    return text


def _description(detail: dict) -> str:
    sections = detail.get("description")

    if not isinstance(sections, dict):
        return strip_html(sections)

    return "\n\n".join(
        text
        for text in (strip_html(value) for value in sections.values())
        if text
    )


def _compensation(detail: dict) -> str:
    ranges = detail.get("payRangeDetails")

    if not ranges:
        return ""

    return json.dumps(ranges, ensure_ascii=False)


def hydrate(job: dict) -> dict | None:
    """Add the date and description after a title matches the user's search."""

    slug = job["company_slug"]
    job_id = job.get("job_id")

    if not job_id:
        return None

    detail = fetch_json(f"{BASE}/{slug}/jobs/{job_id}")

    if not isinstance(detail, dict) or detail.get("unlistedFromSearch") is True:
        return None

    department = detail.get("department")
    department = department if isinstance(department, dict) else {}

    return make_job(
        ats="rippling",
        company=job["company"],
        company_slug=slug,
        job_id=detail.get("uuid") or job_id,
        title=str(detail.get("name") or job.get("title") or "").strip(),
        url=str(detail.get("url") or job.get("url") or "").strip(),
        location=str(job.get("location") or ""),
        team=str(department.get("name") or "").strip(),
        posted_at=detail.get("createdOn"),
        description=_description(detail),
        salary_context=_compensation(detail),
    )


def fetch(company: dict) -> list[dict]:
    slug = company["slug"]
    summaries: list[dict] = []
    seen: set[str] = set()

    for page in range(MAX_PAGES):
        payload = fetch_json(
            f"{BASE}/{slug}/jobs",
            params={
                "groupJobsByLocation": "true",
                "searchQuery": "",
                "page": page,
                "pageSize": PAGE_SIZE,
            },
        )
        items = payload.get("items") if isinstance(payload, dict) else None

        if not isinstance(items, list):
            raise BoardUnavailable("Rippling board returned no job list")

        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue

            job_id = str(item["id"])

            if job_id in seen:
                continue

            seen.add(job_id)
            summaries.append(item)

        total_pages = payload.get("totalPages")

        if (
            not items
            or not isinstance(total_pages, int)
            or page + 1 >= total_pages
        ):
            break

    records = []

    for summary in summaries:
        department = summary.get("department")
        department = department if isinstance(department, dict) else {}

        records.append(
            make_job(
                ats="rippling",
                company=company["name"],
                company_slug=slug,
                job_id=summary["id"],
                title=str(summary.get("name") or "").strip(),
                url=str(summary.get("url") or "").strip(),
                location=_location(summary),
                team=str(department.get("name") or "").strip(),
            )
        )

    return records
