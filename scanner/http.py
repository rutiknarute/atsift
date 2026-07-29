"""
One shared session with retry/backoff, plus error classification.

Thousands of companies are swept per scan, so a dead board must fail fast and
quietly rather than stalling the sweep or spamming the log.
"""

from __future__ import annotations

import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scanner.config import (
    REQUEST_TIMEOUT,
    RETRY_BACKOFF,
    RETRY_TOTAL,
    USER_AGENT,
)

_local = threading.local()


def build_session() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=RETRY_TOTAL,
        status=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=32,
        pool_maxsize=32,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
    )

    return session


def get_session() -> requests.Session:
    """A session per worker thread — requests.Session is not thread-safe."""

    session = getattr(_local, "session", None)

    if session is None:
        session = build_session()
        _local.session = session

    return session


class BoardUnavailable(Exception):
    """The board answered, but not with usable job data."""


def fetch_json(
    url: str,
    *,
    method: str = "GET",
    params: dict | None = None,
    json_body: dict | None = None,
    headers: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
):
    """
    Fetch and decode JSON, or raise BoardUnavailable.

    A 404 means the board slug is wrong or retired — extremely common across a
    17k catalog, and not worth a retry or a stack trace.
    """

    session = get_session()

    try:
        response = session.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as error:
        raise BoardUnavailable(f"request failed: {error}") from error

    if response.status_code == 404:
        raise BoardUnavailable("board not found (404)")

    if response.status_code >= 400:
        raise BoardUnavailable(f"http {response.status_code}")

    try:
        return response.json()
    except ValueError as error:
        raise BoardUnavailable("response was not JSON") from error
