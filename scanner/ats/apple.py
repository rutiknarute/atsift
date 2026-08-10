"""Apple public careers API adapter.

Apple's search API requires a short-lived CSRF token returned in a response
header.  The same thread-local session must make the token and search calls so
the accompanying cookies remain attached.  The ``en-us`` board is explicitly
restricted to Apple's United States location facet, matching the submitted
URL and keeping this high-volume board bounded.
"""

from __future__ import annotations

import json
import re

import requests

from scanner.config import MAX_LOOKBACK_HOURS, REQUEST_TIMEOUT
from scanner.dates import within_window
from scanner.http import BoardUnavailable, fetch_text, get_session
from scanner.records import make_job
from scanner.text import strip_html

BASE = "https://jobs.apple.com"
TOKEN_URL = f"{BASE}/api/v1/CSRFToken"
SEARCH_URL = f"{BASE}/api/v1/search"
PAGE_LIMIT = 20
MAX_PAGES = 250

_HYDRATION = re.compile(
    r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*)"\);\s*</script>',
    re.DOTALL,
)


def _token() -> str:
    session = get_session()

    try:
        response = session.get(TOKEN_URL, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as error:
        raise BoardUnavailable(f"Apple token request failed: {error}") from error

    if response.status_code >= 400:
        raise BoardUnavailable(f"Apple token http {response.status_code}")

    token = str(response.headers.get("x-apple-csrf-token") or "").strip()

    if not token:
        raise BoardUnavailable("Apple token response omitted CSRF token")

    return token


def _page(token: str, page: int) -> dict:
    session = get_session()

    try:
        response = session.post(
            SEARCH_URL,
            json={
                "query": "",
                "filters": {"locations": ["postLocation-USA"]},
                "page": page,
                "locale": "en-us",
                "sort": "",
                "format": {
                    "longDate": "MMMM D, YYYY",
                    "mediumDate": "MMM D, YYYY",
                },
            },
            headers={
                "x-apple-csrf-token": token,
                "browserlocale": "en-us",
                "locale": "en_US",
                "Content-Type": "application/json",
                "Referer": f"{BASE}/en-us/search",
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as error:
        raise BoardUnavailable(f"Apple search failed: {error}") from error

    if response.status_code >= 400:
        raise BoardUnavailable(f"Apple search http {response.status_code}")

    try:
        payload = response.json()
    except ValueError as error:
        raise BoardUnavailable("Apple search response was not JSON") from error

    result = payload.get("res") if isinstance(payload, dict) else None

    return result if isinstance(result, dict) else {}


def _location(job: dict) -> str:
    locations = job.get("locations")
    locations = locations if isinstance(locations, list) else []
    names = [
        str(location.get("name") or "").strip()
        for location in locations
        if isinstance(location, dict)
        and str(location.get("name") or "").strip()
    ]

    return " · ".join(dict.fromkeys(names))


def _url(job: dict) -> str:
    job_id = str(job.get("id") or job.get("positionId") or "").strip()
    title = str(job.get("transformedPostingTitle") or "role").strip()
    team = job.get("team")
    team = team if isinstance(team, dict) else {}
    team_code = str(team.get("teamCode") or "").strip()
    suffix = f"?team={team_code}" if team_code else ""

    return f"{BASE}/en-us/details/{job_id}/{title}{suffix}"


def fetch(company: dict) -> list[dict]:
    token = _token()
    records: list[dict] = []
    seen: set[str] = set()

    for page_number in range(1, MAX_PAGES + 1):
        payload = _page(token, page_number)
        jobs = payload.get("searchResults")

        if not isinstance(jobs, list) or not jobs:
            break

        dates = [job.get("postDateInGMT") for job in jobs if isinstance(job, dict)]

        # Results are newest-first. The product cannot request more than 72
        # hours, so pages wholly older than that ceiling cannot affect a scan.
        if dates and not any(
            within_window(value, MAX_LOOKBACK_HOURS) for value in dates
        ):
            break

        for job in jobs:
            if not isinstance(job, dict):
                continue

            job_id = job.get("id") or job.get("positionId")

            if job_id is None or str(job_id) in seen:
                continue

            seen.add(str(job_id))
            team = job.get("team")
            team = team if isinstance(team, dict) else {}

            records.append(
                make_job(
                    ats="apple",
                    company=company["name"],
                    company_slug=company["slug"],
                    job_id=job_id,
                    title=str(job.get("postingTitle") or "").strip(),
                    url=_url(job),
                    location=_location(job),
                    team=str(team.get("teamName") or "").strip(),
                    posted_at=job.get("postDateInGMT")
                    or job.get("postingDate"),
                    description=str(job.get("jobSummary") or "").strip(),
                )
            )

        if len(jobs) < PAGE_LIMIT:
            break

        total = payload.get("totalRecords")

        if isinstance(total, int) and page_number * PAGE_LIMIT >= total:
            break

    return records


def _hydration(document: str) -> dict:
    match = _HYDRATION.search(str(document or ""))

    if match is None:
        return {}

    try:
        encoded = json.loads(f'"{match.group(1)}"')
        payload = json.loads(encoded)
    except (TypeError, ValueError):
        return {}

    loader = payload.get("loaderData") if isinstance(payload, dict) else None
    detail = loader.get("jobDetails") if isinstance(loader, dict) else None
    data = detail.get("jobsData") if isinstance(detail, dict) else None

    return data if isinstance(data, dict) else {}


def fetch_detail(job: dict) -> str:
    """Fetch qualifications only after a posting survived date/title filters."""

    try:
        data = _hydration(
            fetch_text(job.get("url", ""), headers={"Accept": "text/html"})
        )
    except BoardUnavailable:
        return str(job.get("description") or "")

    parts = [
        data.get("jobSummary"),
        data.get("description"),
        data.get("minimumQualifications"),
        data.get("preferredQualifications"),
    ]

    return strip_html("\n\n".join(str(part or "") for part in parts))
