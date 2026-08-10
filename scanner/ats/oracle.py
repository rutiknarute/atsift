"""Oracle Fusion Recruiting Candidate Experience adapter.

Oracle career sites publish their tenant configuration in the public HTML and
serve structured, paged requisitions through `recruitingCEJobRequisitions`.
The catalog stores the complete Candidate Experience site URL because a single
tenant may expose several independent sites with different site numbers.
"""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse

from scanner.config import MAX_LOOKBACK_HOURS
from scanner.dates import within_window
from scanner.http import BoardUnavailable, fetch_json, fetch_text
from scanner.records import make_job
from scanner.text import strip_html

PAGE_LIMIT = 100
MAX_PAGES = 250


def _site_url(value: str) -> str:
    site = str(value or "").strip().rstrip("/")

    if not site.startswith("http"):
        raise BoardUnavailable("unparseable Oracle Candidate Experience URL")

    return re.sub(r"/(?:jobs?|job)(?:/.*)?$", "", site, flags=re.I)


@lru_cache(maxsize=64)
def _site_config(value: str) -> tuple[str, str, str]:
    site = _site_url(value)
    page = fetch_text(site)
    number = re.search(r'data-sitenumber=["\']([^"\']+)', page, re.I)
    api = re.search(r'data-apibaseurl=["\']([^"\']+)', page, re.I)

    if not number:
        raise BoardUnavailable("Oracle site number not found")

    origin = api.group(1).rstrip("/") if api else ""

    if not origin:
        parsed = urlparse(site)
        origin = f"{parsed.scheme}://{parsed.netloc}"

    return site, origin, number.group(1)


def _locations(job: dict) -> str:
    values = [str(job.get("PrimaryLocation") or "").strip()]

    for key in ("secondaryLocations", "otherWorkLocations"):
        entries = job.get(key)

        if not isinstance(entries, list):
            continue

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            values.append(
                str(
                    entry.get("LocationName")
                    or entry.get("Name")
                    or entry.get("PrimaryLocation")
                    or ""
                ).strip()
            )

    values = [value for value in values if value]

    return " · ".join(dict.fromkeys(values))


def _team(job: dict) -> str:
    values = [
        str(job.get(key) or "").strip()
        for key in ("JobFunction", "JobFamily", "Department", "Category")
    ]

    return " · ".join(dict.fromkeys(value for value in values if value))


def _salary(job: dict) -> str:
    fields = job.get("requisitionFlexFields")

    if not isinstance(fields, list):
        return ""

    values = []

    for field in fields:
        if not isinstance(field, dict):
            continue

        prompt = str(field.get("Prompt") or "").strip()
        value = str(field.get("Value") or "").strip()

        if value and any(
            word in f"{prompt} {value}".casefold()
            for word in ("salary", "compensation", "pay range", "usd")
        ):
            values.append(f"{prompt}: {value}" if prompt else value)

    return " · ".join(dict.fromkeys(values))


def fetch(company: dict) -> list[dict]:
    site, origin, site_number = _site_config(company["slug"])
    endpoint = (
        f"{origin}/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    records: list[dict] = []
    seen: set[str] = set()
    offset = 0

    for _page_number in range(MAX_PAGES):
        payload = fetch_json(
            endpoint,
            params={
                "onlyData": "true",
                "expand": (
                    "requisitionList.workLocation,"
                    "requisitionList.otherWorkLocations,"
                    "requisitionList.secondaryLocations,"
                    "requisitionList.requisitionFlexFields"
                ),
                "finder": (
                    f"findReqs;siteNumber={site_number},limit={PAGE_LIMIT},"
                    f"sortBy=POSTING_DATES_DESC,offset={offset}"
                ),
            },
        )
        wrapper = payload.get("items") if isinstance(payload, dict) else None
        page = wrapper[0] if isinstance(wrapper, list) and wrapper else None
        jobs = page.get("requisitionList") if isinstance(page, dict) else None

        if not isinstance(jobs, list) or not jobs:
            break

        new_jobs = 0

        for job in jobs:
            if not isinstance(job, dict):
                continue

            job_id = str(job.get("Id") or "").strip()

            if not job_id or job_id in seen:
                continue

            seen.add(job_id)
            new_jobs += 1
            records.append(
                make_job(
                    ats="oracle",
                    company=company["name"],
                    company_slug=company["slug"],
                    job_id=job_id,
                    title=str(job.get("Title") or "").strip(),
                    url=f"{site}/job/{job_id}",
                    location=_locations(job),
                    team=_team(job),
                    posted_at=job.get("PostedDate"),
                    description=strip_html(job.get("ShortDescriptionStr")),
                    salary_context=_salary(job),
                )
            )

        if new_jobs == 0:
            break

        dates = [job.get("PostedDate") for job in jobs if job.get("PostedDate")]

        if dates and not any(
            within_window(value, MAX_LOOKBACK_HOURS) for value in dates
        ):
            break

        total = page.get("TotalJobsCount")
        step = page.get("Limit")
        step = step if isinstance(step, int) and step > 0 else len(jobs)
        offset += step

        if len(jobs) < step or isinstance(total, int) and offset >= total:
            break

    return records


def fetch_detail(job: dict) -> str:
    """Fetch requirements-first text for one Oracle requisition."""

    try:
        _site, origin, site_number = _site_config(
            str(job.get("company_slug") or "")
        )
        payload = fetch_json(
            f"{origin}/hcmRestApi/resources/latest/"
            "recruitingCEJobRequisitionDetails",
            params={
                "expand": "all",
                "onlyData": "true",
                "finder": (
                    f'ById;Id="{job.get("job_id")}",'
                    f"siteNumber={site_number}"
                ),
            },
        )
    except BoardUnavailable:
        return ""

    items = payload.get("items") if isinstance(payload, dict) else None
    detail = items[0] if isinstance(items, list) and items else None

    if not isinstance(detail, dict):
        return ""

    sections = [
        ("Qualifications", detail.get("ExternalQualificationsStr")),
        ("Responsibilities", detail.get("ExternalResponsibilitiesStr")),
        ("Description", detail.get("ExternalDescriptionStr")),
        ("Company", detail.get("CorporateDescriptionStr")),
    ]
    text = []

    for label, raw in sections:
        value = strip_html(raw)

        if value:
            text.append(f"{label}\n{value}")

    return "\n\n".join(text)
