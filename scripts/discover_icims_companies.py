"""Discover and verify public iCIMS career portals.

The discovery stage uses Internet Archive CDX indexes only to find candidate
hosts. A candidate enters the scan catalog only after the live host returns an
iCIMS tenant/customer marker. One lightweight listings request then captures
the employer title, current job sample, and visible United States evidence.

Outputs:
  data/companies_icims.csv          scan-ready live portal catalog
  data/icims_boards_reference.csv   rich accepted-board metadata
  data/icims_discovery_audit.csv    accepted and rejected candidates

Existing audit hosts are always used as seeds, so a later rebuild does not
lose a live portal merely because an archive query has changed.

    python3 scripts/discover_icims_companies.py
    python3 scripts/discover_icims_companies.py --target 5000 --workers 32
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import html
import json
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CATALOG_PATH = DATA_DIR / "companies_icims.csv"
REFERENCE_PATH = DATA_DIR / "icims_boards_reference.csv"
AUDIT_PATH = DATA_DIR / "icims_discovery_audit.csv"
WAYBACK_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
USER_AGENT = (
    "Mozilla/5.0 (compatible; JobBoardCatalog/1.0; "
    "public-careers-research)"
)
MAX_METADATA_BYTES = 600_000
ARCHIVE_PATTERNS = (
    r"original:.*\.icims\.com/jobs/search.*",
    r"original:.*\.icims\.com/jobs/intro.*",
)
CATALOG_FIELDS = ["name", "ats", "slug", "source_url"]
REFERENCE_FIELDS = [
    "name",
    "portal_host",
    "source_url",
    "final_url",
    "customer_id",
    "organization_id",
    "tenant_id",
    "x_icims_cid",
    "company_key",
    "production_eligible",
    "exclusion_reason",
    "http_status",
    "metadata_status",
    "live_job_sample_count",
    "us_evidence",
    "verified_at",
]
AUDIT_FIELDS = [
    "portal_host",
    "accepted",
    "http_status",
    "final_url",
    "customer_id",
    "organization_id",
    "tenant_id",
    "x_icims_cid",
    "error",
    "verified_at",
]

_local = threading.local()


def session() -> requests.Session:
    value = getattr(_local, "session", None)

    if value is None:
        value = requests.Session()
        value.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            }
        )
        adapter = requests.adapters.HTTPAdapter(
            max_retries=0,
            pool_connections=1,
            pool_maxsize=1,
        )
        value.mount("https://", adapter)
        _local.session = value

    return value


def _host(url: str) -> str:
    host = str(urlparse(str(url or "")).hostname or "").lower().rstrip(".")

    return host if host.endswith(".icims.com") else ""


def existing_candidates() -> set[str]:
    if not AUDIT_PATH.exists():
        return set()

    with AUDIT_PATH.open(newline="", encoding="utf-8") as handle:
        return {
            str(row.get("portal_host") or "").strip().lower()
            for row in csv.DictReader(handle)
            if str(row.get("portal_host") or "").endswith(".icims.com")
        }


def wayback_candidates() -> set[str]:
    """Read every archived iCIMS search/intro URL with resume pagination."""

    hosts = set()

    for pattern in ARCHIVE_PATTERNS:
        resume_key = ""

        while True:
            params = [
                ("url", "icims.com"),
                ("matchType", "domain"),
                ("output", "json"),
                ("fl", "original"),
                ("filter", "statuscode:200"),
                ("filter", pattern),
                ("collapse", "urlkey"),
                ("limit", "100000"),
                ("showResumeKey", "true"),
            ]

            if resume_key:
                params.append(("resumeKey", resume_key))

            response = requests.get(
                WAYBACK_ENDPOINT,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=240,
            )
            response.raise_for_status()
            payload = response.json()
            resume_key = ""

            for row in payload[1:]:
                if not isinstance(row, list) or len(row) != 1:
                    continue

                value = str(row[0] or "")

                if value.startswith("http"):
                    host = _host(value)

                    if host and ".i.icims.com" not in host:
                        hosts.add(host)
                elif value:
                    resume_key = value

            if not resume_key:
                break

    return hosts


def validate_host(host: str) -> dict:
    url = f"https://{host}/jobs/search?ss=1"

    try:
        response = session().head(
            url,
            timeout=(4, 8),
            allow_redirects=True,
        )
    except requests.RequestException as error:
        return {
            "portal_host": host,
            "accepted": False,
            "error": type(error).__name__,
        }

    headers = {key.lower(): value for key, value in response.headers.items()}
    customer_id = (
        headers.get("icims-ats-customer")
        or headers.get("x-icims-asid")
        or ""
    )
    marker = bool(
        customer_id
        or headers.get("icims-tenant")
        or headers.get("x-icims-cid")
    )

    return {
        "portal_host": host,
        "accepted": response.status_code == 200 and marker,
        "http_status": response.status_code,
        "final_url": response.url,
        "customer_id": customer_id,
        "organization_id": headers.get("icims-organization", ""),
        "tenant_id": headers.get("icims-tenant", ""),
        "x_icims_cid": headers.get("x-icims-cid", ""),
        "error": "" if marker else "missing iCIMS tenant marker",
    }


def _humanize_host(host: str) -> str:
    token = host.removesuffix(".icims.com")
    pieces = token.split("-")
    token = pieces[-1] if len(pieces) > 1 else pieces[0]

    return re.sub(r"[_-]+", " ", token).strip().title() or host


def normalize_name(value: str, host: str) -> str:
    name = str(value or "")

    for _ in range(3):
        decoded = html.unescape(name)

        if decoded == name:
            break

        name = decoded

    name = re.sub(r"\s+", " ", name).strip()
    listings = re.search(
        r"(?:job|internal job|employee job|internship) listings at\s+(.+)$",
        name,
        re.I,
    )

    if listings:
        name = listings.group(1).strip()
    elif re.match(r"^(?:careers?|jobs?|job opportunities)\s*[|:–—-]", name, re.I):
        name = re.split(r"\s*[|:–—-]\s*", name, maxsplit=1)[-1].strip()

    name = re.sub(r"\s*[|–—-]\s*(?:careers?|jobs?)$", "", name, flags=re.I)
    name = name.strip(" |:–—-")

    if len(name) < 3 or name.casefold() in {
        "careers",
        "jobs",
        "job listings at",
        "careers center",
        "careers portal",
    }:
        return _humanize_host(host)

    return name[:240]


def production_exclusion(name: str, host: str) -> str:
    """Reject only unmistakable retired/test portals from active scanning."""

    if name.casefold().startswith("(old)"):
        return "portal title marks it OLD"

    lowered = host.casefold()

    if any(
        marker in lowered
        for marker in (
            "generalmills2test",
            "northwesternmutual2test",
            "zattracttest",
        )
    ):
        return "test portal hostname"

    return ""


def fetch_metadata(row: dict) -> dict:
    host = row["portal_host"]
    source_url = f"https://{host}/jobs/search?ss=1"

    try:
        with session().get(
            f"{source_url}&in_iframe=1",
            timeout=(4, 12),
            allow_redirects=True,
            stream=True,
        ) as response:
            chunks = []
            size = 0

            for chunk in response.iter_content(32_768):
                if not chunk:
                    continue

                chunks.append(chunk)
                size += len(chunk)

                if size >= MAX_METADATA_BYTES:
                    break

            document = b"".join(chunks).decode(
                response.encoding or "utf-8",
                "replace",
            )
            status = response.status_code
    except requests.RequestException as error:
        return {
            **row,
            "name": _humanize_host(host),
            "source_url": source_url,
            "metadata_status": "",
            "metadata_error": type(error).__name__,
            "live_job_sample_count": 0,
            "us_evidence": False,
        }

    soup = BeautifulSoup(document, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    job_ids = {
        match.group(1)
        for match in re.finditer(r"/jobs/(\d+)/[^/?#]+/job", document, re.I)
    }
    visible = soup.get_text(" ", strip=True)
    us_evidence = bool(
        re.search(
            r"(?:\bUS-[A-Z]{2}(?:-|\b)|United States|U\.S\.(?:A\.)?)",
            visible,
            re.I,
        )
    )

    return {
        **row,
        "name": normalize_name(title, host),
        "source_url": source_url,
        "metadata_status": status,
        "metadata_error": "",
        "live_job_sample_count": len(job_ids),
        "us_evidence": us_evidence,
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")

    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    temporary.replace(path)


def write_outputs(validations: list[dict], metadata: list[dict]) -> None:
    verified_at = datetime.now(timezone.utc).date().isoformat()
    metadata_by_host = {row["portal_host"]: row for row in metadata}
    live = []

    for validation in validations:
        validation["verified_at"] = verified_at

        if not validation.get("accepted"):
            continue

        row = metadata_by_host.get(validation["portal_host"], validation)
        row["verified_at"] = verified_at
        row["name"] = normalize_name(
            row.get("name", ""),
            row["portal_host"],
        )
        row["company_key"] = (
            f"customer:{row['customer_id']}"
            if row.get("customer_id")
            else f"tenant:{row['tenant_id']}"
            if row.get("tenant_id")
            else f"host:{row['portal_host']}"
        )
        row["exclusion_reason"] = production_exclusion(
            row["name"],
            row["portal_host"],
        )
        row["production_eligible"] = not bool(row["exclusion_reason"])
        live.append(row)

    live.sort(key=lambda row: (row["name"].casefold(), row["portal_host"]))
    validations.sort(key=lambda row: row["portal_host"])
    catalog = [
        {
            "name": row["name"],
            "ats": "icims",
            "slug": row["portal_host"],
            "source_url": row["source_url"],
        }
        for row in live
        if row["production_eligible"]
    ]
    _write_csv(CATALOG_PATH, CATALOG_FIELDS, catalog)
    _write_csv(REFERENCE_PATH, REFERENCE_FIELDS, live)
    _write_csv(AUDIT_PATH, AUDIT_FIELDS, validations)


def _load_json(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON list in {path}")

    rows = []

    for value in payload:
        if not isinstance(value, dict):
            continue

        row = dict(value)

        if not row.get("portal_host") and row.get("host"):
            row["portal_host"] = row["host"]

        if "accepted" not in row and "live" in row:
            row["accepted"] = bool(row["live"])

        if "http_status" not in row and "status" in row:
            row["http_status"] = row["status"]

        rows.append(row)

    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=5_000)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--validation-json", type=Path)
    parser.add_argument("--metadata-json", type=Path)
    args = parser.parse_args(argv)

    if bool(args.validation_json) != bool(args.metadata_json):
        parser.error("--validation-json and --metadata-json must be used together")

    if args.validation_json:
        validations = _load_json(args.validation_json)
        metadata = _load_json(args.metadata_json)
    else:
        candidates = existing_candidates()
        print("Discovering archived iCIMS portal hosts...", flush=True)
        candidates.update(wayback_candidates())
        print(f"Validating {len(candidates):,} candidates...", flush=True)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.workers
        ) as pool:
            validations = list(pool.map(validate_host, sorted(candidates)))

        accepted = [row for row in validations if row.get("accepted")]
        print(f"Fetching metadata for {len(accepted):,} live portals...", flush=True)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.workers
        ) as pool:
            metadata = list(pool.map(fetch_metadata, accepted))

    live_count = sum(bool(row.get("accepted")) for row in validations)

    metadata_by_host = {
        row.get("portal_host"): row
        for row in metadata
        if row.get("portal_host")
    }
    production_count = sum(
        not production_exclusion(
            str(metadata_by_host.get(row.get("portal_host"), {}).get("name") or ""),
            str(row.get("portal_host") or ""),
        )
        for row in validations
        if row.get("accepted")
    )

    if production_count < args.target:
        print(
            f"Refusing to write: {production_count:,} production portals "
            f"is below "
            f"target {args.target:,}.",
            file=sys.stderr,
        )
        return 1

    write_outputs(validations, metadata)
    us_count = sum(bool(row.get("us_evidence")) for row in metadata)
    print(
        f"Wrote {production_count:,} production iCIMS portals "
        f"from {live_count:,} live portals; "
        f"{us_count:,} show first-page U.S. evidence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
