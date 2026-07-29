"""Job identity and the normalised record every adapter returns."""

from __future__ import annotations

from scanner.boolean_search import ROLE_CATEGORY_LABELS
from scanner.dates import age_hours, parse_timestamp


def job_uid(ats: str, company_slug: str, job_id) -> str:
    """
    Stable identity for a posting: ats:company:job-id.

    The same role can appear under several categories and across re-scans;
    dedup and viewed-tracking both key on this.
    """

    return f"{ats}:{company_slug}:{job_id}"


def make_job(
    *,
    ats: str,
    company: str,
    company_slug: str,
    job_id,
    title: str,
    url: str,
    location: str = "",
    team: str = "",
    posted_at=None,
    description: str = "",
    salary_context: str = "",
    categories: list[str] | None = None,
) -> dict:
    posted = parse_timestamp(posted_at)
    cats = categories or []

    return {
        "uid": job_uid(ats, company_slug, job_id),
        "ats": ats,
        "company": company,
        "company_slug": company_slug,
        "job_id": str(job_id),
        "title": title,
        "url": url,
        "location": location,
        "team": team,
        "posted_at": posted.isoformat() if posted else None,
        "age_hours": age_hours(posted_at),
        "description": description,
        "salary_context": salary_context,
        "categories": cats,
        "category_labels": [
            ROLE_CATEGORY_LABELS[c] for c in cats if c in ROLE_CATEGORY_LABELS
        ],
    }


def dedupe_jobs(jobs: list[dict]) -> list[dict]:
    """Keep the first occurrence of each uid, preserving order."""

    seen: set[str] = set()
    unique: list[dict] = []

    for job in jobs:
        uid = job.get("uid")

        if not uid or uid in seen:
            continue

        seen.add(uid)
        unique.append(job)

    return unique
