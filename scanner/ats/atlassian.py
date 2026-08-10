"""Atlassian's consolidated public career feed.

Atlassian's submitted regional iCIMS portal redirects to its company career
site. Atlassian publishes one JSON endpoint that combines those regional
portals, so the dedicated adapter remains separate from the general iCIMS
HTML adapter.
"""

from __future__ import annotations

from scanner.http import fetch_json
from scanner.records import make_job
from scanner.text import strip_html


DEFAULT_ENDPOINT = "https://www.atlassian.com/endpoint/careers/listings"


def _endpoint(value: str) -> str:
    text = str(value or "").strip()

    return text if text.startswith("http") else DEFAULT_ENDPOINT


def fetch(company: dict) -> list[dict]:
    payload = fetch_json(_endpoint(company["slug"]))

    if not isinstance(payload, list):
        return []

    records = []

    for job in payload:
        if not isinstance(job, dict):
            continue

        portal = job.get("portalJobPost")
        portal = portal if isinstance(portal, dict) else {}
        job_id = job.get("id") or portal.get("id")

        if job_id is None:
            continue

        locations = job.get("locations")
        locations = locations if isinstance(locations, list) else []
        description = strip_html(
            "\n\n".join(
                str(job.get(key) or "")
                for key in (
                    "responsibilities",
                    "qualifications",
                    "overview",
                )
            )
        )

        records.append(
            make_job(
                ats="atlassian",
                company=company["name"],
                company_slug=company["slug"],
                job_id=job_id,
                title=str(job.get("title") or "").strip(),
                url=str(
                    portal.get("portalUrl") or job.get("applyUrl") or ""
                ).strip(),
                location=" · ".join(
                    dict.fromkeys(
                        str(location).strip()
                        for location in locations
                        if str(location or "").strip()
                    )
                ),
                team=str(job.get("category") or "").strip(),
                posted_at=portal.get("updatedDate"),
                description=description,
                salary_context=strip_html(job.get("compensation")),
            )
        )

    return records
