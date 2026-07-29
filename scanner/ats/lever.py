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
    payload = None
    last_error: Exception | None = None

    for host in HOSTS:
        try:
            payload = fetch_json(f"{host}/{slug}", params={"mode": "json"})
            break
        except BoardUnavailable as error:
            last_error = error

    if payload is None:
        raise last_error or BoardUnavailable("lever unavailable")

    if not isinstance(payload, list):
        return []

    records = []

    for job in payload:
        if not isinstance(job, dict):
            continue

        job_id = job.get("id")

        if job_id is None:
            continue

        categories = job.get("categories")
        categories = categories if isinstance(categories, dict) else {}

        records.append(
            make_job(
                ats="lever",
                company=company["name"],
                company_slug=slug,
                job_id=job_id,
                title=str(job.get("text") or "").strip(),
                url=str(job.get("hostedUrl") or job.get("applyUrl") or ""),
                location=str(categories.get("location") or "").strip(),
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

    return records
