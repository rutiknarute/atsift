"""
Adapter dispatch.

Every adapter exposes `fetch(company) -> list[dict]` returning normalised
records. Boards whose list endpoint carries no description also expose
`fetch_detail(job) -> str`, called later and only for postings that already
survived the boolean search and the time window. An adapter whose list also
omits the posting date exposes `hydrate(job) -> dict`; that runs immediately
after a title match so freshness can be decided without hydrating irrelevant
roles.
"""

from __future__ import annotations

from scanner.ats import (
    apple,
    atlassian,
    ashby,
    avature,
    greenhouse,
    ibm,
    icims,
    jibe,
    lever,
    oracle,
    rippling,
    smartrecruiters,
    successfactors,
    workable,
    workday,
)

ADAPTERS = {
    "greenhouse": greenhouse,
    "apple": apple,
    "atlassian": atlassian,
    "ashby": ashby,
    "avature": avature,
    "ibm": ibm,
    "icims": icims,
    "jibe": jibe,
    "lever": lever,
    "oracle": oracle,
    "rippling": rippling,
    "smartrecruiters": smartrecruiters,
    "successfactors": successfactors,
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


def hydrate_job(job: dict) -> dict | None:
    """Fill metadata an ATS omits from its list payload."""

    adapter = ADAPTERS.get(str(job.get("ats") or "").lower())
    hydrate = getattr(adapter, "hydrate", None)

    if hydrate is None:
        return job

    return hydrate(job)


def needs_hydration(ats: str) -> bool:
    adapter = ADAPTERS.get(str(ats or "").lower())

    return hasattr(adapter, "hydrate")


def needs_detail_fetch(ats: str) -> bool:
    adapter = ADAPTERS.get(str(ats or "").lower())

    return hasattr(adapter, "fetch_detail")
