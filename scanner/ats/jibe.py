"""Jibe/iCIMS career-site adapter.

Jibe fronts iCIMS with a public JSON search API.  The catalog stores the
career-site origin because each customer has its own hostname:

    https://careers.amd.com/api/jobs

Unlike the older iCIMS HTML portal, this response already includes the full
description, publish date, locations, categories, and canonical job URL.
"""

from __future__ import annotations

from scanner.http import BoardUnavailable, fetch_json
from scanner.records import make_job
from scanner.text import strip_html

PAGE_LIMIT = 100
MAX_PAGES = 250


def _base_url(value: str) -> str:
    base = str(value or "").strip().rstrip("/")

    if not base.startswith("http"):
        raise BoardUnavailable("unparseable Jibe career-site URL")

    return base


def _team(job: dict) -> str:
    categories = job.get("categories")
    names = []

    if isinstance(categories, list):
        names = [
            str(category.get("name") or "").strip()
            for category in categories
            if isinstance(category, dict)
            and str(category.get("name") or "").strip()
        ]

    department = str(job.get("department") or "").strip()

    if department:
        names.append(department)

    return " · ".join(dict.fromkeys(names))


def _description(job: dict) -> str:
    # Jibe's description is normally the complete posting; its separate
    # fields are overlapping excerpts and concatenating them duplicates most
    # of a long job description. They remain a fallback for sparse tenants.
    description = job.get("description")
    parts = [description] if description else [
        job.get("responsibilities"),
        job.get("qualifications"),
    ]

    return strip_html("\n\n".join(str(part or "") for part in parts))


def _salary(job: dict) -> str:
    values = []

    for index in range(1, 9):
        raw = job.get(f"tags{index}")
        items = raw if isinstance(raw, list) else [raw]
        values.extend(str(item or "").strip() for item in items)

    values = [value for value in values if value and "USD" in value.upper()]

    return " · ".join(dict.fromkeys(values))


def _canonical_url(base: str, job: dict) -> str:
    metadata = job.get("meta_data")
    metadata = metadata if isinstance(metadata, dict) else {}
    canonical = str(metadata.get("canonical_url") or "").strip()

    if canonical:
        return canonical

    slug = str(job.get("slug") or job.get("req_id") or "").strip()
    language = str(job.get("language") or "en-us").strip()

    return f"{base}/jobs/{slug}?lang={language}"


def fetch(company: dict) -> list[dict]:
    base = _base_url(company["slug"])
    records: list[dict] = []
    seen: set[str] = set()
    page = 1

    while page <= MAX_PAGES:
        payload = fetch_json(
            f"{base}/api/jobs",
            params={"limit": PAGE_LIMIT, "page": page},
        )
        jobs = payload.get("jobs") if isinstance(payload, dict) else None

        if not isinstance(jobs, list) or not jobs:
            break

        new_jobs = 0

        for wrapper in jobs:
            job = wrapper.get("data") if isinstance(wrapper, dict) else None

            if not isinstance(job, dict):
                continue

            job_id = job.get("req_id") or job.get("slug")

            if job_id is None or str(job_id) in seen:
                continue

            seen.add(str(job_id))
            new_jobs += 1

            records.append(
                make_job(
                    ats="jibe",
                    company=company["name"],
                    company_slug=company["slug"],
                    job_id=job_id,
                    title=str(job.get("title") or "").strip(),
                    url=_canonical_url(base, job),
                    location=str(
                        job.get("full_location")
                        or job.get("location_name")
                        or ""
                    ).strip(),
                    team=_team(job),
                    posted_at=job.get("posted_date")
                    or job.get("create_date"),
                    description=_description(job),
                    salary_context=_salary(job),
                )
            )

        if new_jobs == 0 or len(jobs) < PAGE_LIMIT:
            break

        total = payload.get("totalCount")

        if isinstance(total, int) and len(seen) >= total:
            break

        page += 1

    return records
