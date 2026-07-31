"""
Lever job board adapter.

Lever runs a separate EU host. The US host answers 404 for EU-hosted accounts,
so a miss there falls back rather than dropping the company.
"""

from __future__ import annotations

from scanner.http import BoardUnavailable, fetch_json
from scanner.records import make_job
from scanner.text import strip_html

HOSTS = (
    "https://api.lever.co/v0/postings",
    "https://api.eu.lever.co/v0/postings",
)
PAGE_LIMIT = 100


def _description(job: dict) -> str:
    parts = [
        job.get("descriptionPlain") or strip_html(job.get("description")),
    ]

    for section in job.get("lists") or []:
        if not isinstance(section, dict):
            continue

        text = strip_html(section.get("content"))

        if text:
            parts.append(f"{section.get('text') or ''}\n{text}".strip())

    parts.append(
        job.get("additionalPlain") or strip_html(job.get("additional"))
    )

    return "\n\n".join(part for part in parts if part).strip()


def fetch(company: dict) -> list[dict]:
    slug = company["slug"]
    last_error: Exception | None = None

    for host in HOSTS:
        records = []
        skip = 0

        while True:
            try:
                payload = fetch_json(
                    f"{host}/{slug}",
                    params={
                        "mode": "json",
                        "limit": PAGE_LIMIT,
                        "skip": skip,
                    },
                )
            except BoardUnavailable as error:
                last_error = error

                if skip == 0:
                    break

                raise

            if not isinstance(payload, list):
                return []

            for job in payload:
                if not isinstance(job, dict):
                    continue

                job_id = job.get("id")

                if job_id is None:
                    continue

                categories = job.get("categories")
                categories = categories if isinstance(categories, dict) else {}
                all_locations = categories.get("allLocations")
                location = (
                    " · ".join(
                        str(item).strip()
                        for item in all_locations
                        if str(item).strip()
                    )
                    if isinstance(all_locations, list)
                    else ""
                )
                location = (
                    location
                    or str(categories.get("location") or "").strip()
                    or (
                        "Remote"
                        if str(job.get("workplaceType") or "").casefold()
                        == "remote"
                        else ""
                    )
                )

                records.append(
                    make_job(
                        ats="lever",
                        company=company["name"],
                        company_slug=slug,
                        job_id=job_id,
                        title=str(job.get("text") or "").strip(),
                        url=str(
                            job.get("applyUrl")
                            or job.get("hostedUrl")
                            or ""
                        ),
                        location=location,
                        team=str(
                            categories.get("team")
                            or categories.get("department")
                            or ""
                        ).strip(),
                        # Lever returns epoch milliseconds.
                        posted_at=job.get("createdAt"),
                        description=_description(job),
                        salary_context=str(job.get("salaryRange") or ""),
                    )
                )

            if len(payload) < PAGE_LIMIT:
                return records

            skip += len(payload)

    if last_error is not None:
        raise last_error

    raise BoardUnavailable("lever unavailable")
