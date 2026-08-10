"""Avature career-portal adapter.

Avature exposes server-rendered result and detail pages rather than a public
JSON feed. The catalog stores the portal root, for example:

    https://jobs.lenovo.com/en_US/careers

Result cards carry a stable requisition number and an explicit posted date.
Descriptions stay on the detail page and are fetched only after a posting has
passed the scanner's title and freshness filters.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from scanner.config import MAX_LOOKBACK_HOURS
from scanner.dates import within_window
from scanner.http import BoardUnavailable, fetch_text
from scanner.records import make_job
from scanner.text import strip_html

PAGE_LIMIT = 10
MAX_PAGES = 250


def _base_url(value: str) -> str:
    base = str(value or "").strip().rstrip("/")

    if not base.startswith("http"):
        raise BoardUnavailable("unparseable Avature portal URL")

    return re.sub(r"/(?:SearchJobs|JobDetail)(?:/.*)?$", "", base)


def _articles(page: str) -> list[str]:
    return re.findall(
        r'<article\b[^>]*class="[^"]*\barticle--result\b[^"]*"[^>]*>'
        r"(.*?)</article>",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)

    return strip_html(match.group(1)) if match else ""


def fetch(company: dict) -> list[dict]:
    base = _base_url(company["slug"])
    records: list[dict] = []
    seen: set[str] = set()
    offset = 0

    for _page_number in range(MAX_PAGES):
        page = fetch_text(
            f"{base}/SearchJobs",
            params={
                "jobRecordsPerPage": PAGE_LIMIT,
                "jobOffset": offset,
            },
        )
        articles = _articles(page)

        if not articles:
            break

        new_jobs = 0

        for article in articles:
            link = re.search(
                r'<a\b[^>]*href="([^"]*?/JobDetail/[^"]+)"[^>]*>'
                r"(.*?)</a>",
                article,
                flags=re.IGNORECASE | re.DOTALL,
            )

            if not link:
                continue

            url = urljoin(base + "/", link.group(1))
            title = strip_html(link.group(2))
            subtitle = _first(
                r'<div\b[^>]*class="[^"]*article__header__text__subtitle'
                r'[^"]*"[^>]*>(.*?)</div>',
                article,
            )
            req = re.search(r"Req\s*#:\s*([^\s]+)", subtitle, re.I)
            posted = re.search(
                r"Posted\s+(\d{1,2}-[A-Za-z]{3}-\d{4})",
                subtitle,
                re.I,
            )
            location = re.split(r"\s+Req\s*#:", subtitle, maxsplit=1)[0]
            team = _first(
                r'<span\b[^>]*class="[^"]*\bparagraph\b[^"]*"[^>]*>'
                r"(.*?)</span>",
                article,
            )
            job_id = req.group(1) if req else url.rstrip("/").rsplit("/", 1)[-1]

            if not job_id or job_id in seen:
                continue

            seen.add(job_id)
            new_jobs += 1
            records.append(
                make_job(
                    ats="avature",
                    company=company["name"],
                    company_slug=company["slug"],
                    job_id=job_id,
                    title=title,
                    url=url,
                    location=location.strip(),
                    team=team,
                    posted_at=posted.group(1) if posted else None,
                    description="",
                )
            )

        if new_jobs == 0 or len(articles) < PAGE_LIMIT:
            break

        dates = [
            record.get("posted_at")
            for record in records[-new_jobs:]
            if record.get("posted_at")
        ]

        if dates and not any(
            within_window(value, MAX_LOOKBACK_HOURS) for value in dates
        ):
            break

        offset += len(articles)

    return records


def fetch_detail(job: dict) -> str:
    """Read the named description section from an Avature detail page."""

    try:
        page = fetch_text(str(job.get("url") or ""))
    except BoardUnavailable:
        return ""

    for article in re.findall(
        r"<article\b[^>]*>(.*?)</article>",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        if "description and requirements" not in strip_html(article).casefold():
            continue

        content = re.search(
            r'<div\b[^>]*class="[^"]*\barticle__content\b[^"]*"[^>]*>'
            r"(.*)",
            article,
            flags=re.IGNORECASE | re.DOTALL,
        )

        text = strip_html(content.group(1) if content else article)

        return re.sub(r"\n +", "\n", text)

    return ""
