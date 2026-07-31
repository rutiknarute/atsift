"""Resolve company logos with Brandfetch and Logo.dev.

Brandfetch search supplies a verified icon/domain when possible. Logo.dev is
the CDN fallback and can also resolve a domain by company name. Provider
credentials never enter stored jobs; only public CDN image URLs do.
"""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import quote, urlparse

import requests

from scanner.config import (
    BRANDFETCH_CLIENT_ID,
    BRANDFETCH_LOGO_CACHE_PATH,
    BRANDFETCH_SECRET_API_KEY,
    LOGO_DEV_PUBLISHABLE_KEY,
    LOGO_DEV_SECRET_KEY,
    REQUEST_TIMEOUT,
)
from scanner.http import get_session
from scanner.jsonio import read_json, write_json

_cache_lock = threading.Lock()
_resolution_lock = threading.Lock()

_ALLOWED_BRANDFETCH_HOSTS = {
    "asset.brandfetch.io",
    "cdn.brandfetch.io",
}
_RESOLVER_VERSION = 2
_GENERIC_COMPANY_WORDS = {
    "and",
    "care",
    "co",
    "company",
    "corp",
    "corporation",
    "group",
    "health",
    "home",
    "holdings",
    "inc",
    "incorporated",
    "limited",
    "llc",
    "ltd",
    "services",
    "technologies",
    "technology",
    "the",
}


def normalize_company_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _safe_domain(value: str | None) -> str:
    text = str(value or "").strip().casefold()

    if text.startswith(("http://", "https://")):
        text = str(urlparse(text).hostname or "")

    text = text.split("/", 1)[0].strip(".")

    if (
        not text
        or len(text) > 253
        or not re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
            r"[a-z]{2,63}",
            text,
        )
    ):
        return ""

    return text


def _safe_brandfetch_icon(value: str | None) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)

    if (
        parsed.scheme != "https"
        or parsed.hostname not in _ALLOWED_BRANDFETCH_HOSTS
    ):
        return ""

    return text


def _company_tokens(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    distinctive = [
        token
        for token in tokens
        if token not in _GENERIC_COMPANY_WORDS
    ]

    return distinctive or tokens


def _candidate_score(company_name: str, result: dict) -> float:
    """Prefer a domain that resembles the company, not merely result order."""

    company_tokens = _company_tokens(company_name)
    company_key = "".join(company_tokens)
    result_name = normalize_company_name(result.get("name"))
    result_key = "".join(_company_tokens(result_name))
    domain = _safe_domain(result.get("domain"))
    domain_labels = domain.split(".")
    domain_stem = (
        domain_labels[1]
        if len(domain_labels) > 1 and domain_labels[0] == "www"
        else domain_labels[0]
    )
    score = 0.0

    if result_name == normalize_company_name(company_name):
        score += 4
    elif company_key and result_key:
        score += 2 * SequenceMatcher(
            None,
            company_key,
            result_key,
        ).ratio()

    if company_key and domain_stem:
        if domain_stem == company_key or domain_stem in company_tokens:
            score += 10
        elif (
            domain_stem.startswith(company_key)
            or company_key.startswith(domain_stem)
        ):
            score += 3

        score += 2 * SequenceMatcher(
            None,
            company_key,
            domain_stem,
        ).ratio()

    if domain.endswith(".com"):
        score += 1

    return score


def _best_result(company_name: str, results: list[dict]) -> dict:
    return max(
        results,
        key=lambda result: _candidate_score(company_name, result),
    )


def logo_dev_url(
    *,
    company_name: str = "",
    domain: str = "",
) -> str | None:
    """Build a public Logo.dev CDN URL without exposing the secret key."""

    if not LOGO_DEV_PUBLISHABLE_KEY:
        return None

    safe_domain = _safe_domain(domain)

    if safe_domain:
        identifier = quote(safe_domain, safe="")
    else:
        name = str(company_name or "").strip()

        if not name:
            return None

        identifier = f"name/{quote(name, safe='')}"

    token = quote(LOGO_DEV_PUBLISHABLE_KEY, safe="")

    return (
        f"https://img.logo.dev/{identifier}"
        f"?token={token}&size=64&retina=true"
        "&format=webp&fallback=404"
    )


def _brandfetch_result(company_name: str) -> dict:
    if not BRANDFETCH_CLIENT_ID and not BRANDFETCH_SECRET_API_KEY:
        return {}

    name = quote(company_name, safe="")
    kwargs: dict = {"timeout": REQUEST_TIMEOUT}

    if BRANDFETCH_CLIENT_ID:
        kwargs["params"] = {"c": BRANDFETCH_CLIENT_ID}
    else:
        kwargs["headers"] = {
            "Authorization": f"Bearer {BRANDFETCH_SECRET_API_KEY}",
        }

    response = get_session().get(
        f"https://api.brandfetch.io/v2/search/{name}",
        **kwargs,
    )
    response.raise_for_status()
    results = response.json()

    if not isinstance(results, list):
        raise ValueError("Brandfetch search returned an invalid response")

    valid = [
        result
        for result in results
        if isinstance(result, dict)
        and (
            _safe_brandfetch_icon(result.get("icon"))
            or _safe_domain(result.get("domain"))
        )
    ]

    if not valid:
        return {}

    selected = _best_result(company_name, valid)

    return {
        "logo_url": _safe_brandfetch_icon(selected.get("icon")) or None,
        "domain": _safe_domain(selected.get("domain")),
        "provider": "brandfetch",
        "_score": _candidate_score(company_name, selected),
    }


def _logo_dev_result(company_name: str) -> dict:
    if not LOGO_DEV_SECRET_KEY:
        return {}

    response = get_session().get(
        "https://api.logo.dev/search",
        params={"q": company_name, "strategy": "match"},
        headers={"Authorization": f"Bearer {LOGO_DEV_SECRET_KEY}"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    results = response.json()

    if not isinstance(results, list):
        raise ValueError("Logo.dev search returned an invalid response")

    valid = [
        result
        for result in results
        if isinstance(result, dict) and _safe_domain(result.get("domain"))
    ]

    if not valid:
        return {}

    selected = _best_result(company_name, valid)

    return {
        "logo_url": None,
        "domain": _safe_domain(selected.get("domain")),
        "provider": "logo.dev",
        "_score": _candidate_score(company_name, selected),
    }


def resolve_company_logo(company_name: str) -> dict:
    try:
        brandfetch = _brandfetch_result(company_name)
    except (requests.RequestException, ValueError):
        brandfetch = {}

    try:
        logo_dev = _logo_dev_result(company_name)
    except (requests.RequestException, ValueError):
        logo_dev = {}

    candidates = [
        result
        for result in (brandfetch, logo_dev)
        if result.get("domain")
    ]
    result = max(
        candidates,
        key=lambda item: (
            float(item.get("_score") or 0),
            item.get("provider") == "brandfetch",
        ),
        default={},
    )

    return {
        "logo_url": result.get("logo_url"),
        "domain": result.get("domain") or "",
        "provider": result.get("provider") or "",
        "resolver_version": _RESOLVER_VERSION,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }


def load_logo_cache() -> dict:
    with _cache_lock:
        cached = read_json(BRANDFETCH_LOGO_CACHE_PATH, {})

    return cached if isinstance(cached, dict) else {}


def _resolve_missing(missing: dict[str, str]) -> None:
    try:
        updates: dict[str, dict] = {}

        with ThreadPoolExecutor(max_workers=min(8, len(missing))) as pool:
            futures = {
                pool.submit(resolve_company_logo, name): key
                for key, name in missing.items()
            }

            for future in as_completed(futures):
                key = futures[future]

                try:
                    updates[key] = future.result()
                except Exception:
                    updates[key] = {
                        "logo_url": None,
                        "domain": "",
                        "provider": "",
                        "resolver_version": _RESOLVER_VERSION,
                        "resolved_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                    }

        if updates:
            with _cache_lock:
                latest = read_json(BRANDFETCH_LOGO_CACHE_PATH, {})
                latest = latest if isinstance(latest, dict) else {}
                latest.update(updates)
                write_json(BRANDFETCH_LOGO_CACHE_PATH, latest)
    finally:
        _resolution_lock.release()


def _schedule_resolution(missing: dict[str, str]) -> None:
    if (
        not missing
        or not (
            BRANDFETCH_CLIENT_ID
            or BRANDFETCH_SECRET_API_KEY
            or LOGO_DEV_SECRET_KEY
        )
        or not _resolution_lock.acquire(blocking=False)
    ):
        return

    thread = threading.Thread(
        target=_resolve_missing,
        args=(missing,),
        daemon=True,
        name="company-logo-resolution",
    )

    try:
        thread.start()
    except RuntimeError:
        _resolution_lock.release()


def prepare_job_logos(jobs: list[dict]) -> list[dict]:
    """Attach primary/fallback image URLs and refresh missing cache entries."""

    cached = load_logo_cache()
    names = {
        normalize_company_name(job.get("company")): str(
            job.get("company") or ""
        ).strip()
        for job in jobs
        if str(job.get("company") or "").strip()
    }
    missing = {
        key: name
        for key, name in names.items()
        if (
            key not in cached
            or (
                isinstance(cached.get(key), dict)
                and cached[key].get("provider")
                and cached[key].get("resolver_version")
                != _RESOLVER_VERSION
            )
        )
    }
    _schedule_resolution(missing)

    for job in jobs:
        company = str(job.get("company") or "").strip()
        entry = cached.get(normalize_company_name(company))
        entry = entry if isinstance(entry, dict) else {}
        brandfetch_url = _safe_brandfetch_icon(entry.get("logo_url"))
        logo_dev = logo_dev_url(
            company_name=company,
            domain=str(entry.get("domain") or ""),
        )

        job["logo_url"] = brandfetch_url or logo_dev
        job["logo_fallback_url"] = (
            logo_dev if brandfetch_url and logo_dev else None
        )

    return jobs
