"""General public iCIMS career-portal adapter.

iCIMS list pages expose job cards as server-rendered HTML. Posting dates and
full descriptions live on each job page as JobPosting JSON-LD, so the scanner
hydrates only titles that already match the user's Boolean search.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from scanner.http import BoardUnavailable, fetch_text
from scanner.records import make_job
from scanner.text import strip_html

MAX_PAGES = 100
JOB_PATH_RE = re.compile(r"/jobs/(\d+)/[^/?#]+/job", re.I)


def _host(value: str) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = str(parsed.hostname or "").lower().rstrip(".")

    if not host.endswith(".icims.com"):
        raise BoardUnavailable("not an iCIMS portal host")

    return host


def _list_url(value: str, page: int = 0) -> str:
    return f"https://{_host(value)}/jobs/search?pr={page}&in_iframe=1"


def _fields(card) -> dict[str, str]:
    fields = {}

    for item in card.select(".iCIMS_JobHeaderTag"):
        label = item.select_one(".iCIMS_JobHeaderField")
        value = item.select_one(".iCIMS_JobHeaderData")

        if label and value:
            key = label.get_text(" ", strip=True).rstrip(":").casefold()
            fields[key] = value.get_text(" ", strip=True)

    for header in card.select(".header"):
        label = header.select_one(".field-label")

        if label:
            key = label.get_text(" ", strip=True).rstrip(":").casefold()
            label.extract()
            fields.setdefault(key, header.get_text(" ", strip=True))

    return fields


def _first(fields: dict[str, str], *names: str) -> str:
    for name in names:
        value = fields.get(name.casefold())

        if value:
            return value

    return ""


def _parse_page(document: str, company: dict) -> tuple[list[dict], int]:
    soup = BeautifulSoup(document, "html.parser")
    records = []

    for card in soup.select(".iCIMS_JobCardItem"):
        link = card.select_one('a[href*="/jobs/"][href*="/job"]')

        if link is None:
            continue

        url = urljoin(_list_url(company["slug"]), str(link.get("href") or ""))
        match = JOB_PATH_RE.search(urlparse(url).path)

        if match is None:
            continue

        title_node = link.select_one("h1, h2, h3")
        title = (
            title_node.get_text(" ", strip=True)
            if title_node is not None
            else link.get_text(" ", strip=True)
        )

        if not title:
            continue

        fields = _fields(card)
        description = card.select_one(".description")
        description_text = (
            description.get_text(" ", strip=True) if description else ""
        )

        records.append(
            make_job(
                ats="icims",
                company=company["name"],
                company_slug=_host(company["slug"]),
                job_id=match.group(1),
                title=title,
                url=url.split("?", 1)[0],
                location=_first(fields, "job location", "location"),
                team=_first(fields, "category", "department", "division"),
                posted_at=_first(fields, "posted date"),
                description=description_text,
                salary_context=_first(
                    fields,
                    "salary range",
                    "pay range",
                    "compensation",
                ),
            )
        )

    last_page = 0

    for link in soup.select('.iCIMS_Paging a[href*="pr="]'):
        query = parse_qs(urlparse(str(link.get("href") or "")).query)

        try:
            last_page = max(last_page, int(query.get("pr", [0])[0]))
        except (TypeError, ValueError):
            continue

    return records, min(last_page, MAX_PAGES - 1)


def _job_posting(document: str) -> dict:
    soup = BeautifulSoup(document, "html.parser")

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue

        candidates = payload if isinstance(payload, list) else [payload]

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            graph = candidate.get("@graph")

            if isinstance(graph, list):
                candidates.extend(graph)

            if str(candidate.get("@type") or "").casefold() == "jobposting":
                return candidate

    return {}


def _json_location(value) -> str:
    locations = value if isinstance(value, list) else [value]
    names = []

    for location in locations:
        if not isinstance(location, dict):
            continue

        address = location.get("address")
        address = address if isinstance(address, dict) else {}
        parts = [
            address.get("addressLocality"),
            address.get("addressRegion"),
            address.get("addressCountry"),
        ]
        text = ", ".join(str(part).strip() for part in parts if part)

        if text:
            names.append(text)

    return " · ".join(dict.fromkeys(names))


def hydrate(job: dict) -> dict | None:
    """Add authoritative date, description, location, and compensation."""

    url = str(job.get("url") or "").strip()

    if not url:
        return None

    document = fetch_text(url, params={"in_iframe": "1"})
    posting = _job_posting(document)

    if not posting:
        return None

    salary = posting.get("baseSalary")
    salary_context = (
        json.dumps(salary, ensure_ascii=False)
        if isinstance(salary, (dict, list))
        else str(salary or job.get("salary_context") or "")
    )

    return make_job(
        ats="icims",
        company=job["company"],
        company_slug=job["company_slug"],
        job_id=job["job_id"],
        title=str(posting.get("title") or job.get("title") or "").strip(),
        url=str(posting.get("url") or url).strip(),
        location=_json_location(posting.get("jobLocation"))
        or str(job.get("location") or ""),
        team=str(
            posting.get("occupationalCategory") or job.get("team") or ""
        ).strip(),
        posted_at=posting.get("datePosted") or job.get("posted_at"),
        description=strip_html(posting.get("description")),
        salary_context=salary_context,
    )


def fetch(company: dict) -> list[dict]:
    document = fetch_text(_list_url(company["slug"]))
    records, last_page = _parse_page(document, company)
    seen = {record["uid"] for record in records}

    for page in range(1, last_page + 1):
        page_records, _ = _parse_page(
            fetch_text(_list_url(company["slug"], page)),
            company,
        )

        for record in page_records:
            if record["uid"] not in seen:
                seen.add(record["uid"])
                records.append(record)

    return records
