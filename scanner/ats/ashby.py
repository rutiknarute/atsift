"""Ashby job board adapter."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from scanner.http import BoardUnavailable, fetch_json, fetch_text
from scanner.records import make_job
from scanner.text import strip_html

BASE = "https://api.ashbyhq.com/posting-api/job-board"
PUBLIC_BASE = "https://jobs.ashbyhq.com"
HTML_DETAIL_WORKERS = 8

_APP_DATA = re.compile(r"window\.__appData\s*=")
_DATE_POSTED = re.compile(r'"datePosted"\s*:\s*"([^"]+)"')


def _compensation(job: dict) -> str:
    compensation = job.get("compensation")

    if not isinstance(compensation, dict):
        return ""

    summary = compensation.get("compensationTierSummary")

    if summary:
        return str(summary).strip()

    return json.dumps(compensation, ensure_ascii=False)


def _fetch_api(company: dict) -> list[dict]:
    slug = company["slug"]

    payload = fetch_json(
        f"{BASE}/{slug}",
        params={"includeCompensation": "true"},
    )

    jobs = payload.get("jobs") if isinstance(payload, dict) else None

    if not isinstance(jobs, list):
        return []

    records = []

    for job in jobs:
        if not isinstance(job, dict):
            continue

        # isListed false means the posting is hidden on the public board.
        if job.get("isListed") is False:
            continue

        job_id = job.get("id")

        if job_id is None:
            continue

        description = job.get("descriptionPlain") or strip_html(
            job.get("descriptionHtml")
        )

        location = str(job.get("location") or "").strip()
        is_remote = (
            bool(job.get("isRemote"))
            or str(job.get("workplaceType") or "").casefold() == "remote"
        )

        if is_remote and "remote" not in location.casefold():
            location = f"{location} · Remote" if location else "Remote"

        records.append(
            make_job(
                ats="ashby",
                company=company["name"],
                company_slug=slug,
                job_id=job_id,
                title=str(job.get("title") or "").strip(),
                url=str(job.get("applyUrl") or job.get("jobUrl") or ""),
                location=location,
                team=str(job.get("team") or job.get("department") or "").strip(),
                posted_at=job.get("publishedAt") or job.get("updatedAt"),
                description=str(description or ""),
                salary_context=_compensation(job),
            )
        )

    return records


def _app_data(document: str) -> dict:
    """Decode Ashby's server-rendered bootstrap object from a public page."""

    match = _APP_DATA.search(str(document or ""))

    if match is None:
        raise BoardUnavailable("Ashby page has no app data")

    remainder = document[match.end():].lstrip()

    try:
        payload, _ = json.JSONDecoder().raw_decode(remainder)
    except (TypeError, ValueError) as error:
        raise BoardUnavailable("Ashby page app data is invalid") from error

    if not isinstance(payload, dict):
        raise BoardUnavailable("Ashby page app data is invalid")

    return payload


def _html_posted_at(document: str):
    """Best public posting date on API-disabled boards (day precision)."""

    match = _DATE_POSTED.search(str(document or ""))

    return match.group(1) if match else None


def _html_location(posting: dict) -> str:
    locations = [posting.get("locationName")]
    locations.extend(posting.get("secondaryLocationNames") or [])
    locations = [
        str(value).strip()
        for value in locations
        if str(value or "").strip()
    ]
    location = " · ".join(dict.fromkeys(locations))
    is_remote = str(posting.get("workplaceType") or "").casefold() == "remote"

    if is_remote and "remote" not in location.casefold():
        location = f"{location} · Remote" if location else "Remote"

    return location


def _fetch_html_posting(
    company: dict,
    board_url: str,
    summary: dict,
) -> dict | None:
    job_id = summary.get("id")

    if not job_id:
        return None

    job_url = f"{board_url.rstrip('/')}/{quote(str(job_id), safe='')}"
    document = fetch_text(job_url, headers={"Accept": "text/html"})
    posting = _app_data(document).get("posting")

    if not isinstance(posting, dict) or posting.get("isListed") is False:
        return None

    teams = posting.get("teamNames") or []
    team = " · ".join(
        dict.fromkeys(
            str(value).strip()
            for value in teams
            if str(value or "").strip()
        )
    )

    return make_job(
        ats="ashby",
        company=company["name"],
        company_slug=company["slug"],
        job_id=job_id,
        title=str(posting.get("title") or summary.get("title") or "").strip(),
        url=job_url,
        location=_html_location(posting),
        team=team or str(posting.get("departmentName") or "").strip(),
        posted_at=_html_posted_at(document),
        description=strip_html(posting.get("descriptionHtml")),
        salary_context=str(posting.get("compensationTierSummary") or "").strip(),
    )


def _safe_fetch_html_posting(
    company: dict,
    board_url: str,
    summary: dict,
) -> dict | None:
    try:
        return _fetch_html_posting(company, board_url, summary)
    except Exception:
        # A single removed posting can race the board listing. Preserve every
        # other role instead of discarding the entire company.
        return None


def _fetch_html_board(company: dict) -> list[dict]:
    """
    Read an Ashby board whose organization disabled the posting API.

    Ashby's public HTML still contains the complete listing in
    ``window.__appData``. Individual public job pages add the description,
    teams, compensation, and a JSON-LD ``datePosted`` value. The detail calls
    are parallel because the list payload does not expose posting dates.
    """

    slug = str(company["slug"])
    canonical_url = f"{PUBLIC_BASE}/{quote(slug, safe='')}/"
    source_url = str(company.get("source_url") or "").strip()
    board_url = (
        source_url
        if source_url.startswith(f"{PUBLIC_BASE}/")
        else canonical_url
    )
    payload = _app_data(
        fetch_text(board_url, headers={"Accept": "text/html"})
    )
    board = payload.get("jobBoard")
    summaries = board.get("jobPostings") if isinstance(board, dict) else None

    if not isinstance(summaries, list):
        raise BoardUnavailable("Ashby page has no job listing")

    with ThreadPoolExecutor(max_workers=HTML_DETAIL_WORKERS) as pool:
        records = pool.map(
            lambda summary: _safe_fetch_html_posting(
                company,
                board_url,
                summary,
            ),
            (summary for summary in summaries if isinstance(summary, dict)),
        )

        return [record for record in records if record is not None]


def fetch(company: dict) -> list[dict]:
    try:
        return _fetch_api(company)
    except BoardUnavailable:
        # Some organizations deliberately disable Ashby's posting API even
        # though their public jobs.ashbyhq.com board remains fully usable.
        return _fetch_html_board(company)
