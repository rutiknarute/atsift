"""
Workday job board adapter.

Workday has no uniform slug — every tenant is its own host, which is why the
Workday catalog stores a full board URL and lives in a separate dataset.

    https://23andme.wd5.myworkdayjobs.com/23
            tenant   host                  board

The public read API sits at a derived path:

    https://<host>/wday/cxs/<tenant>/<board>/jobs   (POST, paged)

Dates come back as human text ("Posted 3 Days Ago"), so they need parsing
rather than a timestamp parse.
"""

from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import urlparse

from scanner.dates import now_utc
from scanner.http import BoardUnavailable, fetch_json
from scanner.records import make_job
from scanner.text import strip_html

PAGE_LIMIT = 20
MAX_PAGES = 5

_RELATIVE = re.compile(
    r"(\d+)\s*\+?\s*(day|days|hour|hours|week|weeks|month|months)",
    re.IGNORECASE,
)


def parse_board_url(slug: str) -> tuple[str, str, str] | None:
    """Split a Workday board URL into (host, tenant, board)."""

    text = str(slug or "").strip()

    if not text:
        return None

    if not text.startswith("http"):
        text = f"https://{text}"

    parsed = urlparse(text)
    host = parsed.netloc

    if not host or "myworkdayjobs.com" not in host:
        return None

    tenant = host.split(".")[0]
    segments = [part for part in parsed.path.split("/") if part]

    if not segments:
        return None

    # Paths sometimes carry a locale prefix: /en-US/BoardName
    board = segments[-1]

    return host, tenant, board


def parse_posted_on(value) -> object:
    """
    Turn "Posted 3 Days Ago" into a timestamp.

    "Posted Today" and "Posted Yesterday" are common; "30+ Days Ago" is
    treated as exactly 30 days, which is well outside any window we support so
    the imprecision cannot change an answer.
    """

    text = str(value or "").strip().lower()

    if not text:
        return None

    now = now_utc()

    if "today" in text:
        return now

    if "yesterday" in text:
        return now - timedelta(days=1)

    match = _RELATIVE.search(text)

    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2).lower()

    if unit.startswith("hour"):
        return now - timedelta(hours=amount)

    if unit.startswith("day"):
        return now - timedelta(days=amount)

    if unit.startswith("week"):
        return now - timedelta(weeks=amount)

    return now - timedelta(days=amount * 30)


def fetch(company: dict) -> list[dict]:
    parsed = parse_board_url(company["slug"])

    if parsed is None:
        raise BoardUnavailable("unparseable workday board url")

    host, tenant, board = parsed
    endpoint = f"https://{host}/wday/cxs/{tenant}/{board}/jobs"
    origin = f"https://{host}"

    records: list[dict] = []
    offset = 0

    for _ in range(MAX_PAGES):
        payload = fetch_json(
            endpoint,
            method="POST",
            json_body={
                "appliedFacets": {},
                "limit": PAGE_LIMIT,
                "offset": offset,
                "searchText": "",
            },
            headers={"Content-Type": "application/json"},
        )

        postings = (
            payload.get("jobPostings") if isinstance(payload, dict) else None
        )

        if not isinstance(postings, list) or not postings:
            break

        for job in postings:
            if not isinstance(job, dict):
                continue

            external_path = str(job.get("externalPath") or "")
            job_id = (
                job.get("bulletFields")
                and job["bulletFields"][0]
                or external_path
                or job.get("title")
            )

            if not job_id:
                continue

            records.append(
                make_job(
                    ats="workday",
                    company=company["name"],
                    company_slug=company["slug"],
                    job_id=job_id,
                    title=str(job.get("title") or "").strip(),
                    url=f"{origin}{external_path}" if external_path else origin,
                    location=str(job.get("locationsText") or "").strip(),
                    team="",
                    posted_at=parse_posted_on(job.get("postedOn")),
                    description="",
                )
            )

        if len(postings) < PAGE_LIMIT:
            break

        offset += PAGE_LIMIT

    return records


def fetch_detail(job: dict) -> str:
    """Fetch one posting's description. Empty string on failure."""

    parsed = parse_board_url(job.get("company_slug", ""))

    if parsed is None:
        return ""

    host, tenant, board = parsed
    url = str(job.get("url") or "")
    path = urlparse(url).path

    if not path:
        return ""

    try:
        payload = fetch_json(f"https://{host}/wday/cxs/{tenant}/{board}{path}")
    except BoardUnavailable:
        return ""

    info = payload.get("jobPostingInfo") if isinstance(payload, dict) else None

    if not isinstance(info, dict):
        return ""

    return strip_html(info.get("jobDescription"))
