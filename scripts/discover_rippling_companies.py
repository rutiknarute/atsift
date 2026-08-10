"""
Discover and verify a standalone Rippling company catalog.

Candidates come from public indexes plus the repository's existing company
names/slugs. A candidate is kept only when Rippling's public v2 board API
answers with a real job-list payload and the public board page exposes a
company name. Obvious test/demo boards and duplicate company names are
removed. The destination is replaced only after the requested minimum has
been reached.

    python3 scripts/discover_rippling_companies.py
    python3 scripts/discover_rippling_companies.py --target 2000
    python3 scripts/discover_rippling_companies.py --workers 24
"""

from __future__ import annotations

import argparse
import csv
import gzip
import html
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scanner.config import DATA_DIR  # noqa: E402

API_BASE = "https://ats.rippling.com/api/v2/board"
PUBLIC_BASE = "https://ats.rippling.com"
SOURCEGRAPH = "https://sourcegraph.com/.api/search/stream"
COMMON_CRAWL_INFO = "https://index.commoncrawl.org/collinfo.json"
COMMON_CRAWL_DATA = "https://data.commoncrawl.org/cc-index/collections"
URLSCAN = "https://urlscan.io/api/v1/search/"
ALIENVAULT = (
    "https://otx.alienvault.com/api/v1/indicators/hostname/"
    "ats.rippling.com/url_list"
)
OUTPUT = DATA_DIR / "companies_rippling.csv"
FIELDS = ["name", "ats", "slug", "source_url"]

DEFAULT_TARGET = 2_000
DEFAULT_WORKERS = 24
REQUEST_TIMEOUT = 30
INDEX_TIMEOUT = 300
RETRYABLE = {429, 500, 502, 503, 504}

_URL_TOKEN = re.compile(
    r"ats(?:\.us1)?\.rippling\.com/([A-Za-z0-9][A-Za-z0-9._~-]*)/jobs",
    re.IGNORECASE,
)
_VALID_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._~-]{0,159}$")
_NEXT_DATA = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_PLACEHOLDER = re.compile(
    r"(^|[-_\s])(acme|demo|sandbox|test|testing)([-_\s]|$)",
    re.IGNORECASE,
)
_SPACE = re.compile(r"\s+")

_local = threading.local()


def _session() -> requests.Session:
    session = getattr(_local, "session", None)

    if session is None:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "ATSift-RipplingCatalog/1.0",
                "Accept": "application/json",
            }
        )
        _local.session = session

    return session


def _get(
    url: str,
    *,
    params: dict | None = None,
    timeout=REQUEST_TIMEOUT,
    stream: bool = False,
):
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            response = _session().get(
                url,
                params=params,
                timeout=timeout,
                stream=stream,
            )
        except requests.RequestException as error:
            last_error = error
            time.sleep(0.4 * (attempt + 1))
            continue

        if response.status_code not in RETRYABLE:
            return response

        response.close()
        time.sleep(0.4 * (attempt + 1))

    if last_error is not None:
        raise last_error

    return response


def _token(value: str) -> str | None:
    token = str(value or "").strip().casefold()

    if not _VALID_TOKEN.fullmatch(token):
        return None

    return token


def _tokens_from_text(value: str) -> set[str]:
    return {
        token
        for match in _URL_TOKEN.finditer(str(value or ""))
        if (token := _token(match.group(1))) is not None
    }


def sourcegraph_candidates() -> set[str]:
    query = (
        "context:global ats.rippling.com count:all "
        "archived:yes fork:yes"
    )
    response = _get(
        SOURCEGRAPH,
        params={"q": query, "v": "V3"},
        timeout=INDEX_TIMEOUT,
    )

    if response.status_code != 200:
        return set()

    # Matches live inside JSON-encoded SSE records, so normalise the two
    # escape forms that can split an otherwise ordinary URL.
    text = response.text.replace(r"\u0026", "&").replace(r"\/", "/")

    return _tokens_from_text(text)


def _token_from_index_url(value: str) -> str | None:
    path = [part for part in urlparse(str(value or "")).path.split("/") if part]

    if "jobs" not in path:
        return None

    jobs_index = path.index("jobs")

    if jobs_index < 1:
        return None

    return _token(path[jobs_index - 1])


def _common_crawl_collection(index_id: str) -> set[str]:
    """Read one domain slice directly from Common Crawl's CDX files."""

    base = f"{COMMON_CRAWL_DATA}/{index_id}/indexes"
    cluster = _get(
        f"{base}/cluster.idx",
        timeout=INDEX_TIMEOUT,
        stream=True,
    )

    if cluster.status_code != 200:
        return set()

    target = b"com,rippling,ats)/"
    upper = b"com,rippling,ats)0"
    previous: bytes | None = None
    blocks: list[bytes] = []

    # cluster.idx is sorted. Stop as soon as the Rippling domain range ends;
    # this reads roughly 40 MB instead of the full 100+ MB secondary index.
    for line in cluster.iter_lines(chunk_size=1024 * 1024):
        if not line:
            continue

        first_field = line.split(b"\t", 1)[0]
        url_key = first_field.rsplit(b" ", 1)[0]

        if url_key >= target:
            if not blocks and previous is not None:
                blocks.append(previous)

            if url_key >= upper:
                break

            blocks.append(line)

        previous = line

    cluster.close()

    candidates: set[str] = set()

    for line in blocks:
        try:
            fields = line.decode("utf-8").split("\t")
            filename = fields[1]
            offset = int(fields[2])
            length = int(fields[3])
        except (IndexError, UnicodeDecodeError, ValueError):
            continue

        response = _session().get(
            f"{base}/{filename}",
            headers={"Range": f"bytes={offset}-{offset + length - 1}"},
            timeout=INDEX_TIMEOUT,
        )

        if response.status_code not in {200, 206}:
            continue

        try:
            content = gzip.decompress(response.content).decode(
                "utf-8",
                "replace",
            )
        except (OSError, UnicodeDecodeError):
            continue

        for raw_record in content.splitlines():
            try:
                record = json.loads(raw_record.split(" ", 2)[2])
            except (IndexError, ValueError):
                continue

            token = _token_from_index_url(record.get("url"))

            if token:
                candidates.add(token)

    return candidates


def common_crawl_candidates(max_indexes: int = 2) -> set[str]:
    # The public query service can rate-limit broad domain requests. Its
    # collection manifest is tiny, and the underlying CDX range is public, so
    # fall back to known recent IDs if even the manifest is unavailable.
    indexes: list[str] = []

    try:
        response = _get(COMMON_CRAWL_INFO, timeout=REQUEST_TIMEOUT)

        if response.status_code == 200:
            indexes = [
                str(item.get("id"))
                for item in response.json()
                if isinstance(item, dict) and item.get("id")
            ]
    except (requests.RequestException, ValueError):
        pass

    if not indexes:
        indexes = ["CC-MAIN-2026-30", "CC-MAIN-2026-25"]

    preferred = indexes[1:2] + indexes[:1] + indexes[2:]
    candidates: set[str] = set()

    for index_id in preferred[:max_indexes]:
        print(f"    scanning {index_id}...", flush=True)

        try:
            candidates.update(_common_crawl_collection(index_id))
        except requests.RequestException:
            continue

    return candidates


def search_index_candidates() -> set[str]:
    candidates: set[str] = set()

    try:
        response = _get(
            URLSCAN,
            params={"q": "domain:ats.rippling.com", "size": 10_000},
        )

        if response.status_code == 200:
            for result in response.json().get("results") or []:
                candidates.update(_tokens_from_text(json.dumps(result)))
    except (requests.RequestException, ValueError):
        pass

    try:
        response = _get(ALIENVAULT, params={"limit": 5_000})

        if response.status_code == 200:
            candidates.update(_tokens_from_text(response.text))
    except requests.RequestException:
        pass

    return candidates


def _slugify(value: str) -> str | None:
    text = str(value or "").casefold()
    text = re.sub(r"[’']s\b", "s", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")

    return _token(text)


def local_candidates() -> list[str]:
    candidates: set[str] = set()

    for path in DATA_DIR.glob("companies*.csv"):
        if path == OUTPUT:
            continue

        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                for value in (row.get("slug"), _slugify(row.get("name"))):
                    token = _token(value)

                    if token:
                        candidates.add(token)

    return sorted(candidates)


def board_resolves(token: str) -> bool:
    try:
        response = _get(
            f"{API_BASE}/{token}/jobs",
            params={
                "groupJobsByLocation": "true",
                "page": 0,
                "pageSize": 1,
            },
        )
    except requests.RequestException:
        return False

    if response.status_code != 200:
        return False

    try:
        payload = response.json()
    except ValueError:
        return False

    return isinstance(payload, dict) and isinstance(payload.get("items"), list)


def company_name(token: str) -> str | None:
    try:
        response = _get(
            f"{PUBLIC_BASE}/{token}/jobs",
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    match = _NEXT_DATA.search(response.text)

    if match is None:
        return None

    try:
        payload = json.loads(html.unescape(match.group(1)))
        board = payload["props"]["pageProps"]["apiData"]["jobBoard"]
    except (KeyError, TypeError, ValueError):
        return None

    name = _SPACE.sub(
        " ",
        str(board.get("companyName") or board.get("title") or "").strip(),
    )
    name = re.sub(r"[’']s Job Board$", "", name, flags=re.IGNORECASE).strip()

    if (
        len(name) < 3
        or len(name) > 200
        or not name[0].isalnum()
        or "<" in name
        or ">" in name
    ):
        return None

    if _PLACEHOLDER.search(name) or _PLACEHOLDER.search(token):
        return None

    return name


def _parallel(items, function, workers: int, label: str):
    values = list(items)
    results = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(function, value): value for value in values}

        for completed, future in enumerate(as_completed(futures), 1):
            value = futures[future]

            try:
                result = future.result()
            except Exception:
                result = None

            results.append((value, result))

            if completed % 250 == 0 or completed == len(values):
                accepted = sum(bool(item[1]) for item in results)
                print(
                    f"  {label}: {completed}/{len(values)} "
                    f"({accepted} accepted)",
                    flush=True,
                )

    return results


def verified_companies(tokens: set[str], workers: int) -> dict[str, str]:
    resolved = {
        token
        for token, valid in _parallel(
            sorted(tokens),
            board_resolves,
            workers,
            "live boards",
        )
        if valid
    }
    named = _parallel(
        sorted(resolved),
        company_name,
        workers,
        "company names",
    )

    return {token: name for token, name in named if name}


def _dedupe_companies(companies: dict[str, str]) -> list[dict]:
    chosen: dict[str, tuple[str, str]] = {}

    for token, name in companies.items():
        key = name.casefold()
        current = chosen.get(key)

        # Prefer the simplest token when one company has legacy/alternate
        # boards. It is more likely to be the canonical public URL.
        if current is None or (len(token), token) < (len(current[0]), current[0]):
            chosen[key] = (token, name)

    return sorted(
        (
            {
                "name": name,
                "ats": "rippling",
                "slug": token,
                "source_url": f"{PUBLIC_BASE}/{token}/jobs",
            }
            for token, name in chosen.values()
        ),
        key=lambda row: (row["name"].casefold(), row["slug"]),
    )


def write_catalog(rows: list[dict], output: Path) -> None:
    temporary = output.with_suffix(output.suffix + ".tmp")
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(temporary, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    temporary.replace(output)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--common-crawl-indexes", type=int, default=2)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    if args.target < 1 or args.workers < 1:
        parser.error("--target and --workers must be positive")

    print("Discovering indexed Rippling boards...", flush=True)
    indexed = set()

    sources = (
        ("Sourcegraph", sourcegraph_candidates),
        (
            "Common Crawl",
            lambda: common_crawl_candidates(args.common_crawl_indexes),
        ),
        ("search indexes", search_index_candidates),
    )

    for label, discover in sources:
        try:
            found = discover()
        except Exception as error:
            print(f"  {label}: unavailable ({error})", flush=True)
            continue

        before = len(indexed)
        indexed.update(found)
        print(
            f"  {label}: {len(found)} found, {len(indexed) - before} new",
            flush=True,
        )

    print(f"Verifying {len(indexed)} indexed candidates...", flush=True)
    companies = verified_companies(indexed, args.workers)
    rows = _dedupe_companies(companies)
    checked = set(indexed)

    if len(rows) < args.target:
        fallback = [
            token for token in local_candidates() if token not in checked
        ]
        batch_size = 1_000

        for start in range(0, len(fallback), batch_size):
            batch = set(fallback[start:start + batch_size])
            checked.update(batch)
            print(
                f"Verifying local fallback batch {start // batch_size + 1}...",
                flush=True,
            )
            companies.update(verified_companies(batch, args.workers))
            rows = _dedupe_companies(companies)
            print(f"  distinct companies: {len(rows)}", flush=True)

            if len(rows) >= args.target:
                break

    if len(rows) < args.target:
        print(
            f"Refusing to write: found {len(rows)} distinct live companies, "
            f"below target {args.target}.",
            file=sys.stderr,
        )
        return 1

    write_catalog(rows, args.output)
    print(
        f"Wrote {len(rows)} distinct live Rippling companies to "
        f"{args.output}",
        flush=True,
    )
    print(
        "Run scripts/consolidate_company_datasets.py to refresh the "
        "authoritative external ATS catalog.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
