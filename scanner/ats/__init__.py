"""
Adapter dispatch.

Every adapter exposes `fetch(company) -> list[dict]` returning normalised
records. Boards whose list endpoint carries no description also expose
`fetch_detail(job) -> str`, called later and only for postings that already
survived the boolean search and the time window.
"""

from __future__ import annotations

from scanner.ats import (
    ashby,
    greenhouse,
    lever,
    smartrecruiters,
    workable,
    workday,
)

ADAPTERS = {
    "greenhouse": greenhouse,
    "ashby": ashby,
    "lever": lever,
    "smartrecruiters": smartrecruiters,
    "workable": workable,
    "workday": workday,
}

SUPPORTED_ATS = tuple(ADAPTERS)


def fetch_company(company: dict) -> list[dict]:
    adapter = ADAPTERS.get(str(company.get("ats") or "").lower())

    if adapter is None:
        return []

    return adapter.fetch(company)


def fetch_description(job: dict) -> str:
    """Late description fetch for boards that need a second request."""

    adapter = ADAPTERS.get(str(job.get("ats") or "").lower())
    detail = getattr(adapter, "fetch_detail", None)

    if detail is None:
        return str(job.get("description") or "")

    return detail(job)


def needs_detail_fetch(ats: str) -> bool:
    adapter = ADAPTERS.get(str(ats or "").lower())

    return hasattr(adapter, "fetch_detail")
