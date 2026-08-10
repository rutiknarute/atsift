"""IBM scoped career-search adapter.

IBM's legacy ``careers.ibm.com`` detail template is WAF protected, while its
public careers search uses IBM's own scoped search API.  That API includes the
job identifier, publish date, full HTML body, location, function, and public
detail URL for every current posting.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from scanner.http import fetch_json
from scanner.records import make_job
from scanner.text import strip_html

BASE = (
    "https://www-api.ibm.com/search/api/v1/ibmcom/appid/careers/"
    "responseFormat/json"
)
PAGE_LIMIT = 100
MAX_PAGES = 100


def _attributes(job: dict) -> dict:
    result = {}
    attributes = job.get("docattributes")

    if not isinstance(attributes, list):
        return result

    for item in attributes:
        if isinstance(item, dict):
            result.update(item)

    return result


def _job_id(job: dict, attributes: dict):
    if attributes.get("field_text_01"):
        return attributes["field_text_01"]

    query = parse_qs(urlparse(str(job.get("url") or "")).query)

    return (query.get("jobId") or [job.get("id")])[0]


def fetch(company: dict) -> list[dict]:
    records: list[dict] = []
    seen: set[str] = set()
    offset = 0
    pages = 0

    while pages < MAX_PAGES:
        payload = fetch_json(
            BASE,
            params={
                "scope": "careers2",
                "rmdt": "ALL",
                "appid": "careers",
                "sortby": "-dcdate",
                "fr": offset,
                "nr": PAGE_LIMIT,
                "query": "",
                "cc": "us",
                "lang": "en",
                "sm": "false",
            },
        )
        resultset = payload.get("resultset") if isinstance(payload, dict) else None
        search = (
            resultset.get("searchresults")
            if isinstance(resultset, dict)
            else None
        )
        jobs = search.get("searchresultlist") if isinstance(search, dict) else None

        if not isinstance(jobs, list) or not jobs:
            break

        pages += 1
        new_jobs = 0

        for job in jobs:
            if not isinstance(job, dict):
                continue

            attributes = _attributes(job)
            job_id = _job_id(job, attributes)

            if job_id is None or str(job_id) in seen:
                continue

            seen.add(str(job_id))
            new_jobs += 1

            records.append(
                make_job(
                    ats="ibm",
                    company=company["name"],
                    company_slug=company["slug"],
                    job_id=job_id,
                    title=str(job.get("title") or "").strip(),
                    url=str(job.get("url") or "").strip(),
                    location=str(attributes.get("field_keyword_19") or "").strip(),
                    team=str(attributes.get("field_keyword_08") or "").strip(),
                    posted_at=attributes.get("dcdate"),
                    description=strip_html(
                        attributes.get("raw_body") or job.get("description")
                    ),
                )
            )

        if new_jobs == 0 or len(jobs) < PAGE_LIMIT:
            break

        offset += PAGE_LIMIT
        total = search.get("totalresults")

        if isinstance(total, int) and offset >= total:
            break

    return records
