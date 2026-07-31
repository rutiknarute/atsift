"""
Workday job board adapter.

Workday has no uniform slug — every tenant is its own host, which is why the
Workday catalog stores a full board URL and lives in a separate dataset.

    https://23andme.wd5.myworkdayjobs.com/23
            tenant   host                  board

The public read API sits at a derived path:

    https://<host>/wday/cxs/<tenant>/<board>/jobs   (POST, paged)

Each posting's `externalPath` is relative to the *board*, not to the host, so
the apply URL is <origin>/<board><externalPath> — dropping the board segment
gives a link that 404s.

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
MAX_PAGES = 250

_RELATIVE = re.compile(
    r"(\d+)\s*\+?\s*(day|days|hour|hours|week|weeks|month|months)",
    re.IGNORECASE,
)

# A Workday path may carry a locale prefix: /en-US/BoardName/job/...
_LOCALE = re.compile(r"^[a-z]{2}(-[A-Za-z]{2,4})?$")


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


def posting_url(origin: str, board: str, raw_path: str) -> str:
    """
    The public URL a candidate can actually open.

    `externalPath` from the CXS API is relative to the *board*, not to the
    host — "/job/Austin-TX/Data-Analyst_JR1". Hung off the bare origin it
    404s, so the board segment has to be put back.

    Normalises through `external_path` first, so a tenant that ever returns a
    path already carrying its board cannot produce "/board/board/job/...".
    """

    path = external_path(raw_path, board)

    if not path:
        return f"{origin}/{board}"

    return f"{origin}/{board}{path}"


def external_path(path: str, board: str) -> str:
    """
    Recover the API-relative path from a public URL.

    The inverse of `posting_url`. Tolerates a locale prefix, and a URL stored
    before the board segment was included, so old records keep resolving.
    """

    segments = [part for part in str(path or "").split("/") if part]

    if segments and _LOCALE.match(segments[0]):
        segments = segments[1:]

    if segments and segments[0].casefold() == board.casefold():
        segments = segments[1:]

    if not segments:
        return ""

    return "/" + "/".join(segments)


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
    seen_job_ids: set[str] = set()
    offset = 0
    pages = 0

    while pages < MAX_PAGES:
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

        pages += 1
        new_jobs = 0

        for job in postings:
            if not isinstance(job, dict):
                continue

            path = str(job.get("externalPath") or "")
            job_id = (
                job.get("bulletFields")
                and job["bulletFields"][0]
                or path
                or job.get("title")
            )

            if not job_id:
                continue

            job_key = str(job_id)

            if job_key in seen_job_ids:
                continue

            seen_job_ids.add(job_key)
            new_jobs += 1

            records.append(
                make_job(
                    ats="workday",
                    company=company["name"],
                    company_slug=company["slug"],
                    job_id=job_id,
                    title=str(job.get("title") or "").strip(),
                    url=posting_url(origin, board, path),
                    location=str(job.get("locationsText") or "").strip(),
                    team="",
                    posted_at=parse_posted_on(job.get("postedOn")),
                    description="",
                )
            )

        # A few broken tenants ignore the requested offset and repeat page
        # one forever. Stop as soon as a full response adds nothing new.
        if new_jobs == 0:
            break

        if len(postings) < PAGE_LIMIT:
            break

        offset += PAGE_LIMIT

        total = payload.get("total")

        if isinstance(total, int) and offset >= total:
            break

    return records


def fetch_detail(job: dict) -> str:
    """Fetch one posting's description. Empty string on failure."""

    parsed = parse_board_url(job.get("company_slug", ""))

    if parsed is None:
        return ""

    host, tenant, board = parsed
    url = str(job.get("url") or "")
    path = external_path(urlparse(url).path, board)

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
