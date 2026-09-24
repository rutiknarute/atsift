"""SAP SuccessFactors Recruiting Marketing adapter.

SuccessFactors exposes paginated, server-rendered search HTML. Search rows have
titles, locations, and stable detail URLs but no publish timestamp; detail
pages expose schema.org ``datePosted`` and the complete description.  The
adapter therefore hydrates only title-matched jobs, just like Rippling.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from scanner.http import BoardUnavailable, fetch_text
from scanner.records import make_job

PAGE_LIMIT = 25
MAX_PAGES = 250

_TOTAL = re.compile(r"of\s*<b>\s*([\d,]+)\s*</b>", re.IGNORECASE)
_JOB_ID = re.compile(r"/(\d+)/?$")
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def _classes(attributes: dict[str, str]) -> set[str]:
    return set(str(attributes.get("class") or "").split())


class _SearchParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self.row: dict | None = None
        self.row_depth = 0
        self.capture: str | None = None
        self.capture_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = _classes(attributes)

        if tag == "tr" and "data-row" in classes:
            self.row = {"title": "", "href": "", "location": ""}
            self.row_depth = 1
            return

        if self.row is None:
            return

        self.row_depth += 1

        if (
            tag == "a"
            and "jobTitle-link" in classes
            and not self.row["href"]
        ):
            self.row["href"] = str(attributes.get("href") or "")
            self.capture = "title"
            self.capture_depth = self.row_depth
        elif (
            tag == "span"
            and "jobLocation" in classes
            and not self.row["location"]
        ):
            self.capture = "location"
            self.capture_depth = self.row_depth

    def handle_endtag(self, tag):
        if self.row is None:
            return

        if self.capture and self.row_depth == self.capture_depth:
            self.capture = None

        self.row_depth -= 1

        if tag == "tr" and self.row_depth == 0:
            if self.row["href"] and self.row["title"]:
                self.rows.append(self.row)

            self.row = None

    def handle_data(self, data):
        if self.row is not None and self.capture:
            self.row[self.capture] += data


class _DetailParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.date_posted = ""
        self.description_parts: list[str] = []
        self.description_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)

        if attributes.get("itemprop") == "datePosted":
            self.date_posted = str(attributes.get("content") or "").strip()

        if self.description_depth and tag not in _VOID_TAGS:
            self.description_depth += 1
        elif attributes.get("itemprop") == "description":
            self.description_depth = 1

        if self.description_depth and tag in {"br", "p", "li", "h1", "h2", "h3"}:
            self.description_parts.append("\n")

    def handle_endtag(self, tag):
        if not self.description_depth or tag in _VOID_TAGS:
            return

        if tag in {"p", "li", "h1", "h2", "h3"}:
            self.description_parts.append("\n")

        self.description_depth -= 1

    def handle_data(self, data):
        if self.description_depth:
            self.description_parts.append(data)

    @property
    def description(self) -> str:
        text = "".join(self.description_parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*\n\s*", "\n", text)

        return text.strip()


def _base_url(value: str) -> str:
    base = str(value or "").strip().rstrip("/")

    if not base.startswith("http"):
        raise BoardUnavailable("unparseable SuccessFactors career-site URL")

    return base


def fetch(company: dict) -> list[dict]:
    base = _base_url(company["slug"])
    records: list[dict] = []
    seen: set[str] = set()
    offset = 0

    for _page in range(MAX_PAGES):
        document = fetch_text(
            f"{base}/search/",
            params={
                "q": "",
                "sortColumn": "referencedate",
                "sortDirection": "desc",
                "startrow": offset,
            },
            headers={"Accept": "text/html"},
        )
        parser = _SearchParser()
        parser.feed(document)

        if not parser.rows:
            break

        new_jobs = 0

        for row in parser.rows:
            url = urljoin(f"{base}/", row["href"])
            match = _JOB_ID.search(url)
            job_id = match.group(1) if match else url

            if job_id in seen:
                continue

            seen.add(job_id)
            new_jobs += 1

            records.append(
                make_job(
                    ats="successfactors",
                    company=company["name"],
                    company_slug=company["slug"],
                    job_id=job_id,
                    title=" ".join(row["title"].split()),
                    url=url,
                    location=" ".join(row["location"].split()),
                    posted_at=None,
                    description="",
                )
            )

        if new_jobs == 0 or len(parser.rows) < PAGE_LIMIT:
            break

        offset += PAGE_LIMIT
        total_match = _TOTAL.search(document)

        if total_match and offset >= int(total_match.group(1).replace(",", "")):
            break

    return records


def hydrate(job: dict) -> dict | None:
    try:
        document = fetch_text(
            job.get("url", ""),
            headers={"Accept": "text/html"},
        )
    except BoardUnavailable:
        return None

    parser = _DetailParser()
    parser.feed(document)

    if not parser.date_posted:
        return None

    return make_job(
        ats="successfactors",
        company=job["company"],
        company_slug=job["company_slug"],
        job_id=job["job_id"],
        title=job["title"],
        url=job["url"],
        location=job.get("location", ""),
        team=job.get("team", ""),
        posted_at=parser.date_posted,
        description=parser.description,
        categories=job.get("categories", []),
    )
