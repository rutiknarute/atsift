"""
SmartRecruiters job board adapter.

The list endpoint has no descriptions — those need one extra request per
posting. `fetch_detail` is therefore separate, and the scan layer calls it only
for postings that already passed the boolean search and the time window.
"""

from __future__ import annotations

from scanner.http import BoardUnavailable, fetch_json
from scanner.records import make_job
from scanner.text import strip_html

BASE = "https://api.smartrecruiters.com/v1/companies"

PAGE_LIMIT = 100


def _location(job: dict) -> str:
    location = job.get("location")

    if not isinstance(location, dict):
        return ""

    parts = [
        str(location.get("city") or "").strip(),
        str(location.get("region") or "").strip(),
        str(location.get("country") or "").strip().upper(),
    ]

    text = ", ".join(part for part in parts if part)

    if location.get("remote"):
        text = f"Remote — {text}" if text else "Remote"

    return text


def fetch(company: dict) -> list[dict]:
    slug = company["slug"]
    records: list[dict] = []
    offset = 0

    while True:
        payload = fetch_json(
            f"{BASE}/{slug}/postings",
            params={"limit": PAGE_LIMIT, "offset": offset},
        )

        content = payload.get("content") if isinstance(payload, dict) else None

        if not isinstance(content, list) or not content:
            break

        for job in content:
            if not isinstance(job, dict):
                continue

            job_id = job.get("id")

            if job_id is None:
                continue

            department = job.get("department")
            department = department if isinstance(department, dict) else {}

            records.append(
                make_job(
                    ats="smartrecruiters",
                    company=company["name"],
                    company_slug=slug,
                    job_id=job_id,
                    title=str(job.get("name") or "").strip(),
                    url=str(
                        job.get("applyUrl")
                        or job.get("ref")
                        or f"https://jobs.smartrecruiters.com/{slug}/{job_id}"
                    ),
                    location=_location(job),
                    team=str(department.get("label") or "").strip(),
                    posted_at=job.get("releasedDate")
                    or job.get("createdOn"),
                    description="",
                )
            )

        if len(content) < PAGE_LIMIT:
            break

        offset += PAGE_LIMIT

        total = payload.get("totalFound")

        if isinstance(total, int) and offset >= total:
            break

    return records


def fetch_detail(job: dict) -> str:
    """Fetch the description for one posting. Empty string on failure."""

    try:
        payload = fetch_json(
            f"{BASE}/{job['company_slug']}/postings/{job['job_id']}"
        )
    except BoardUnavailable:
        return ""

    job_ad = payload.get("jobAd") if isinstance(payload, dict) else None
    sections = job_ad.get("sections") if isinstance(job_ad, dict) else None

    if not isinstance(sections, dict):
        return ""

    parts = []

    # Put requirements before company boilerplate. Analysis reads a bounded
    # prefix, and a long employer introduction must not truncate the actual
    # qualifications or experience requirement.
    for key in (
        "jobDescription",
        "qualifications",
        "additionalInformation",
        "companyDescription",
    ):
        section = sections.get(key)

        if isinstance(section, dict):
            title = str(section.get("title") or "").strip()
            text = strip_html(section.get("text"))

            if text:
                parts.append(f"{title}\n{text}".strip())

    return strip_html("\n\n".join(parts))
