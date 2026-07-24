from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import threading
import time
import webbrowser
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from threading import Timer
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv(Path(__file__).resolve().with_name(".env"))


# ============================================================
# GENERAL CONFIGURATION
# ============================================================

DEFAULT_LOOKBACK_HOURS = 48
ALLOWED_LOOKBACK_HOURS = (1, 2, 4, 6, 12, 24, 48, 72)
MAX_STORED_HOURS = max(ALLOWED_LOOKBACK_HOURS)

COMPANY_LIST_FILE = "companies.csv"
FOCUSED_COMPANY_LIST_FILE = "companies_2500.csv"
VERIFIED_US_COMPANY_LIST_FILE = "companies_verified_us.csv"
SEED_COMPANY_LIST_FILE = "companies_seed.csv"
DEFAULT_COMPANY_DATASET = "full"
COMPANY_DATASETS = {
    "full": {
        "label": "Data 16,401",
        "filename": COMPANY_LIST_FILE,
    },
    "focused_2500": {
        "label": "Data 2500",
        "filename": FOCUSED_COMPANY_LIST_FILE,
    },
    "verified_us": {
        "label": "Data 8,011",
        "filename": VERIFIED_US_COMPANY_LIST_FILE,
    },
    "seed_data": {
        "label": "Data 1,952",
        "filename": SEED_COMPANY_LIST_FILE,
    },
}
SUPPORTED_ATS = (
    "greenhouse",
    "ashby",
    "lever",
    "smartrecruiters",
    "workable",
    "workday",
)

JOBS_STORE_FILE = "jobs_store.json"
VIEWED_JOBS_FILE = "viewed_jobs.json"
ANALYSIS_CACHE_FILE = "analysis_cache.json"
BRANDFETCH_LOGO_CACHE_FILE = "brandfetch_logo_cache.json"
SCAN_STATUS_FILE = "scan_status.json"

GREENHOUSE_DETAIL_DELAY_SEC = 0.08
FETCH_WORKERS = max(
    1,
    min(
        32,
        int(os.getenv("ATSIFT_FETCH_WORKERS", "15")),
    ),
)
ATS_PAGE_SIZE = 100
WORKDAY_PAGE_SIZE = 20

TIMEOUT = 20
LOGO_DEV_PUBLISHABLE_KEY = os.getenv(
    "LOGO_DEV_PUBLISHABLE_KEY",
    "",
).strip()
BRANDFETCH_SECRET_API_KEY = os.getenv(
    "BRANDFETCH_SECRET_API_KEY",
    "",
).strip()

DISPLAY_TIMEZONE = "America/Los_Angeles"

AUTO_OPEN_BROWSER = (
    os.getenv("AUTO_OPEN_BROWSER", "false")
    .strip()
    .lower()
    in {"1", "true", "yes"}
)
HOST = os.getenv("JOB_RADAR_HOST", "127.0.0.1")
PORT = int(os.getenv("JOB_RADAR_PORT", "5000"))


# ============================================================
# ROLE CATEGORY TITLE FILTERS
# ============================================================

STANDARD_EXCLUDE_KEYWORDS = [
    "senior",
    "sr",
    "lead",
    "staff",
    "manager",
    "principal",
    "director",
    "vp",
    "vice president",
    "embedded",
    "phd",
    "head",
    "architect",
]

GTM_EXCLUDE_KEYWORDS = [
    "senior",
    "sr",
    "lead",
    "staff",
    "manager",
    "principal",
    "director",
    "vp",
    "vice president",
    "embedded",
    "phd",
    "head",
    "recruiter",
]

ROLE_CATEGORY_KEYWORDS = {
    "software": [
        "software",
        "AI software",
        "application developer",
        "SDE",
        "full stack",
        "frontend",
        "front end",
        "backend",
        "back end",
        "web developer",
        "UI",
        "full-stack",
        "platform engineer",
        "SWE",
        "product engineer",
        "associate developer",
        "application",
        "python",
        "university",
    ],
    "new_grad": [
        "new grad",
        "new graduate",
        "recent graduate",
        "recent grad",
        "college graduate",
        "entry level",
        "entry-level",
        "early career",
        "early careers",
        "university graduate",
        "graduate program",
        "graduate role",
        "graduate",
        "early talent",
        "grad",
        "MS",
        "Co-op",
        "masters",
    ],
    "data_analyst": [
        "data analyst",
        "data analytics",
        "AI data",
        "business analyst",
        "business data",
        "business intelligence",
        "BI analyst",
        "reporting analyst",
        "data reporting",
        "analytics analyst",
        "insights analyst",
        "data insights analyst",
        "product analyst",
        "operations analyst",
        "quantitative analyst",
        "data quality analyst",
        "data governance",
        "data visualization",
        "dashboard analyst",
        "SQL",
        "Excel",
        "tableau",
        "power BI",
        "analytics consultant",
        "data consultant",
    ],
    "data_engineer": [
        "data engineer",
        "data engineering",
        "data developer",
        "data pipeline",
        "big data",
        "ETL",
        "ELT",
        "data integration",
        "data warehouse",
        "informatica",
        "data migration",
        "data platform",
        "analytics engineer",
        "data ingestion",
        "Junior Data",
        "Associate Data",
        "data operations",
        "Cloud Data",
        "database developer",
        "Snowflake",
        "data lake",
    ],
    "ai_ml": [
        "AI Engineer",
        "AI/ML",
        "GenAI",
        "Applied Scientist",
        "LLM",
        "Gen AI",
        "Generative AI",
        "Forward Deployed",
        "Forward-Deployed",
        "FDE",
        "fine tuning",
        "Applied Science",
        "Visual Data",
        "Data Annotator",
        "Data Labeling",
        "AI Trainer",
        "RLHF Specialist",
        "Training Data",
        "Annotation Analyst",
        "AI Data",
        "Data Quality",
        "Data Labeler",
        "Data Annotation",
    ],
    "gtm": [
        "GTM",
        "Go-To-Market",
        "Growth",
        "RevOps Engineer",
        "Founding",
        "AI Automation",
        "AI Workflow",
        "Prompt Engineer",
        "AI Product",
        "AI Solutions",
        "AI Operations",
        "Marketing Operations",
        "Product Growth",
        "Product Operations",
        "Claude",
        "Marketing Technology",
        "Codex",
        "Automation Engineer",
        "Workflow Automation",
        "RAG",
        "Prompt Engineering",
    ],
}

ROLE_CATEGORY_LABELS = {
    "software": "Software",
    "new_grad": "New Grad",
    "data_analyst": "Data Analyst",
    "data_engineer": "Data Engineer",
    "ai_ml": "AI / ML",
    "gtm": "GTM",
}

ROLE_CATEGORY_EXCLUDES = {
    category: (
        GTM_EXCLUDE_KEYWORDS
        if category == "gtm"
        else STANDARD_EXCLUDE_KEYWORDS
    )
    for category in ROLE_CATEGORY_KEYWORDS
}


def compile_keyword_pattern(keywords: list[str]) -> re.Pattern[str]:
    """
    Create a boundary-safe keyword pattern.

    Examples:
        UI will not match build.
        sr will not match SRE.
        lead will not match leaderboard.
    """

    escaped = [
        re.escape(keyword.strip())
        for keyword in sorted(
            set(keywords),
            key=len,
            reverse=True,
        )
        if keyword.strip()
    ]

    return re.compile(
        r"(?<!\w)(?:" + "|".join(escaped) + r")(?!\w)",
        re.IGNORECASE,
    )


ROLE_CATEGORY_PATTERNS = {
    category: (
        compile_keyword_pattern(keywords),
        compile_keyword_pattern(
            ROLE_CATEGORY_EXCLUDES[category]
        ),
    )
    for category, keywords in ROLE_CATEGORY_KEYWORDS.items()
}


def title_categories(title: str | None) -> list[str]:
    """Return every requested role category matched by a job title."""

    if not title:
        return []

    return [
        category
        for category, (
            include_pattern,
            exclude_pattern,
        ) in ROLE_CATEGORY_PATTERNS.items()
        if (
            include_pattern.search(title)
            and not exclude_pattern.search(title)
        )
    ]


def title_matches_keywords(title: str | None) -> bool:
    """Return True when at least one requested role category matches."""

    return bool(title_categories(title))


# ============================================================
# OLLAMA CONFIGURATION
# ============================================================

USE_OLLAMA_ANALYSIS = True

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.2:3b"

MAX_DESCRIPTION_CHARS = 8_000

# Change this when changing the prompt or response format.
# It forces old cached analyses to be regenerated.
ANALYSIS_PROMPT_VERSION = "job-analysis-v5-us-location"


JOB_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "us_location_eligible": {
            "type": "string",
            "enum": ["YES", "NO"],
        },
        "opt_eligible": {
            "type": "string",
            "enum": ["YES", "NO"],
        },
        "opt_blocking_line": {
            "type": "string",
        },
        "degree": {
            "type": "string",
        },
        "qualifications": {
            "type": "string",
        },
        "eligibility": {
            "type": "string",
        },
        "key_tech_skills": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 15,
        },
        "experience_years": {
            "type": "string",
        },
        "minimum_years": {
            "type": ["number", "null"],
        },
        "ats_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "tip": {
            "type": "string",
        },
        "salary": {
            "type": "string",
        },
        "team": {
            "type": "string",
        },
    },
    "required": [
        "us_location_eligible",
        "opt_eligible",
        "opt_blocking_line",
        "degree",
        "qualifications",
        "eligibility",
        "key_tech_skills",
        "experience_years",
        "minimum_years",
        "ats_keywords",
        "tip",
        "salary",
        "team",
    ],
}


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

COMPANIES_PATH = BASE_DIR / COMPANY_LIST_FILE
COMPANY_DATASET_PATHS = {
    dataset_id: BASE_DIR / str(config["filename"])
    for dataset_id, config in COMPANY_DATASETS.items()
}
JOBS_STORE_PATH = BASE_DIR / JOBS_STORE_FILE
VIEWED_JOBS_PATH = BASE_DIR / VIEWED_JOBS_FILE
ANALYSIS_CACHE_PATH = BASE_DIR / ANALYSIS_CACHE_FILE
BRANDFETCH_LOGO_CACHE_PATH = (
    BASE_DIR / BRANDFETCH_LOGO_CACHE_FILE
)
SCAN_STATUS_PATH = BASE_DIR / SCAN_STATUS_FILE

DISPLAY_TZ = ZoneInfo(DISPLAY_TIMEZONE)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

scan_lock = threading.Lock()
status_lock = threading.Lock()
viewed_jobs_lock = threading.Lock()
brandfetch_logo_cache_lock = threading.Lock()
brandfetch_logo_resolution_lock = threading.Lock()
session_local = threading.local()


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path: Path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    except (OSError, json.JSONDecodeError) as error:
        print(f"[warn] Could not read {path.name}: {error}")
        return default


def save_json_atomic(path: Path, data) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

    temporary_path.replace(path)


def canonical_job_uid(uid: str) -> str:
    """Normalize the case-insensitive portions of an internal job UID."""

    parts = uid.strip().split(":", 2)

    if len(parts) != 3:
        return uid.strip()

    source, slug, job_id = parts
    return f"{source.casefold()}:{slug.casefold()}:{job_id}"


def job_identity(job: dict) -> str | None:
    """Return a stable identity even when an ATS slug changes casing."""

    source = str(job.get("source") or "").strip().casefold()
    slug = str(job.get("slug") or "").strip().casefold()
    job_id = str(job.get("id") or "").strip()

    if source and slug and job_id:
        return f"{source}:{slug}:{job_id}"

    uid = canonical_job_uid(str(job.get("uid") or ""))

    if uid:
        return f"uid:{uid}"

    for key in ("apply_url", "job_url"):
        url = str(job.get(key) or "").strip()

        if url:
            return f"url:{url}"

    return None


def deduplicate_jobs(jobs: list[dict]) -> list[dict]:
    """Merge duplicate postings while retaining the freshest record."""

    jobs_by_identity: dict[str, dict] = {}
    jobs_without_identity: list[dict] = []

    for original_job in jobs:
        job = dict(original_job)
        identity = job_identity(job)

        if identity is None:
            jobs_without_identity.append(job)
            continue

        previous = jobs_by_identity.get(identity)

        if previous is None:
            jobs_by_identity[identity] = job
            continue

        previous_seen_at = parse_iso_datetime(
            previous.get("last_seen_at")
        )
        current_seen_at = parse_iso_datetime(
            job.get("last_seen_at")
        )
        current_is_fresher = (
            previous_seen_at is None
            or (
                current_seen_at is not None
                and current_seen_at >= previous_seen_at
            )
        )
        fresher = job if current_is_fresher else previous
        older = previous if current_is_fresher else job
        merged = {**older, **fresher}

        discovered_values = [
            str(value)
            for value in (
                previous.get("discovered_at"),
                job.get("discovered_at"),
            )
            if value
        ]
        viewed_values = [
            str(value)
            for value in (
                previous.get("viewed_at"),
                job.get("viewed_at"),
            )
            if value
        ]

        if discovered_values:
            merged["discovered_at"] = min(discovered_values)

        if viewed_values:
            merged["viewed_at"] = min(viewed_values)

        jobs_by_identity[identity] = merged

    return [*jobs_by_identity.values(), *jobs_without_identity]


# ============================================================
# COMPANY CSV
# ============================================================

def _file_signature(path: Path) -> tuple[str, int, int]:
    resolved_path = path.resolve()
    stat = resolved_path.stat()
    return (
        str(resolved_path),
        stat.st_mtime_ns,
        stat.st_size,
    )


@lru_cache(maxsize=12)
def _load_companies_cached(
    path_value: str,
    _modified_ns: int,
    _file_size: int,
) -> list[dict[str, str]]:
    path = Path(path_value)
    companies: list[dict[str, str]] = []

    with path.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        required_columns = {"name", "ats", "slug"}
        actual_columns = set(reader.fieldnames or [])

        missing_columns = required_columns - actual_columns

        if missing_columns:
            raise ValueError(
                "companies.csv is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row_number, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            ats = (row.get("ats") or "").strip().lower()
            slug = (row.get("slug") or "").strip()

            if not name or not ats or not slug:
                print(
                    f"[warn] Skipping incomplete companies.csv "
                    f"row {row_number}"
                )
                continue

            if ats not in SUPPORTED_ATS:
                print(
                    f"[warn] Skipping unsupported ATS '{ats}' "
                    f"on companies.csv row {row_number}"
                )
                continue

            companies.append(
                {
                    "name": name,
                    "ats": ats,
                    "slug": slug,
                }
            )

    return companies


def load_companies(path: Path) -> list[dict[str, str]]:
    """Load a CSV catalog once per file version.

    Callers treat the returned records as read-only. The mtime and size in
    the cache key automatically invalidate the catalog when a CSV changes.
    """

    return _load_companies_cached(
        *_file_signature(path)
    )


@lru_cache(maxsize=12)
def _company_keys_cached(
    path_value: str,
    modified_ns: int,
    file_size: int,
) -> frozenset[tuple[str, str]]:
    return frozenset(
        (
            company["ats"].casefold(),
            company["slug"].casefold(),
        )
        for company in _load_companies_cached(
            path_value,
            modified_ns,
            file_size,
        )
    )


def company_keys_for_path(
    path: Path,
) -> frozenset[tuple[str, str]]:
    return _company_keys_cached(
        *_file_signature(path)
    )


def company_counts_by_ats(
    companies: list[dict[str, str]],
) -> dict[str, int]:
    counts = {ats: 0 for ats in SUPPORTED_ATS}

    for company in companies:
        counts[company["ats"]] += 1

    return counts


def company_dataset_catalogs() -> list[dict]:
    catalogs: list[dict] = []

    for dataset_id, config in COMPANY_DATASETS.items():
        companies = load_companies(
            COMPANY_DATASET_PATHS[dataset_id]
        )
        catalogs.append(
            {
                "id": dataset_id,
                "label": config["label"],
                "companies": len(companies),
                "companies_by_ats": company_counts_by_ats(
                    companies
                ),
            }
        )

    return catalogs


# ============================================================
# DATE HELPERS
# ============================================================

def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def is_recent(
    value: str | None,
    hours: int,
) -> bool:
    parsed = parse_iso_datetime(value)

    if parsed is None:
        return False

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=hours)
    )

    if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return parsed.date() >= cutoff.date()

    return parsed >= cutoff


def unix_milliseconds_to_iso(value) -> str | None:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return None

    try:
        return datetime.fromtimestamp(
            milliseconds / 1000,
            tz=timezone.utc,
        ).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def lookback_cutoff_iso(hours: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def relative_time(value: str | None) -> str:
    parsed = parse_iso_datetime(value)

    if parsed is None:
        return "Not provided"

    difference = datetime.now(timezone.utc) - parsed
    seconds = max(0, int(difference.total_seconds()))

    if seconds < 60:
        return "Just now"

    minutes = seconds // 60

    if minutes < 60:
        return (
            f"{minutes} minute"
            f"{'' if minutes == 1 else 's'} ago"
        )

    hours = minutes // 60

    if hours < 24:
        remaining_minutes = minutes % 60
        hour_text = (
            f"{hours} hour"
            f"{'' if hours == 1 else 's'}"
        )

        if remaining_minutes == 0:
            return f"{hour_text} ago"

        minute_text = (
            f"{remaining_minutes} minute"
            f"{'' if remaining_minutes == 1 else 's'}"
        )

        return f"{hour_text} {minute_text} ago"

    days = hours // 24

    return (
        f"{days} day"
        f"{'' if days == 1 else 's'} ago"
    )


def display_timestamp(
    value: str | None,
) -> dict[str, str | bool]:
    parsed = parse_iso_datetime(value)

    if parsed is None:
        return {
            "available": False,
            "relative": "Not provided",
            "absolute": "",
        }

    local_time = parsed.astimezone(DISPLAY_TZ)

    date_text = (
        f"{local_time.strftime('%b')} "
        f"{local_time.day}, "
        f"{local_time.year}"
    )

    clock_text = local_time.strftime("%I:%M %p").lstrip("0")

    return {
        "available": True,
        "relative": relative_time(value),
        "absolute": (
            f"{date_text} at {clock_text} "
            f"{local_time.tzname()}"
        ),
    }


# ============================================================
# TEXT HELPERS
# ============================================================

def strip_html(raw_html: str | None) -> str:
    if not raw_html:
        return ""

    text = re.sub(
        r"<(br|/p|/li|/h[1-6])[^>]*>",
        "\n",
        raw_html,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"<[^>]+>", " ", text)

    text = html.unescape(text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()


def join_text_parts(values) -> str:
    parts: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = str(value or "").strip()
        normalized = text.lower()

        if not text or normalized in seen:
            continue

        seen.add(normalized)
        parts.append(text)

    return "\n\n".join(parts)


def labeled_value(value) -> str:
    if isinstance(value, dict):
        return str(
            value.get("label")
            or value.get("name")
            or ""
        ).strip()

    return str(value or "").strip()


def location_parts(*values) -> str:
    parts: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = str(value or "").strip()
        normalized = text.lower()

        if not text or normalized in seen:
            continue

        seen.add(normalized)
        parts.append(text)

    return ", ".join(parts)


def compact_text(
    value,
    default: str = "Not listed.",
    maximum: int = 260,
) -> str:
    text = str(value or "").strip()

    if not text:
        return default

    text = re.sub(r"\s+", " ", text)

    if len(text) > maximum:
        return text[: maximum - 1].rstrip() + "…"

    return text


def compact_list(
    value,
    maximum_items: int = 20,
) -> list[str]:
    if not isinstance(value, list):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()

    for item in value:
        text = compact_text(
            item,
            default="",
            maximum=80,
        )

        normalized = text.lower()

        if not text or normalized in seen:
            continue

        seen.add(normalized)
        cleaned.append(text)

        if len(cleaned) >= maximum_items:
            break

    return cleaned


def department_names(value) -> str:
    if not isinstance(value, list):
        return ""

    names: list[str] = []

    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()

            if name:
                names.append(name)

    return ", ".join(names)


def location_name(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()

    return str(value or "").strip()


US_STATE_NAMES = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "district of columbia",
    "puerto rico",
    "guam",
    "u.s. virgin islands",
}

US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "GU", "VI",
}

# These markers let the scanner discard clearly foreign jobs before invoking
# Ollama. City-only locations are intentionally left undecided for the model,
# because names such as Cambridge exist both inside and outside the U.S.
NON_US_LOCATION_TERMS = {
    "afghanistan",
    "africa",
    "albania",
    "algeria",
    "andorra",
    "angola",
    "antigua and barbuda",
    "apac",
    "argentina",
    "armenia",
    "asia",
    "australia",
    "austria",
    "azerbaijan",
    "bahamas",
    "bahrain",
    "bangladesh",
    "barbados",
    "belarus",
    "belgium",
    "belize",
    "benin",
    "bhutan",
    "bolivia",
    "bosnia and herzegovina",
    "botswana",
    "brazil",
    "brasil",
    "brunei",
    "bulgaria",
    "burkina faso",
    "burundi",
    "cambodia",
    "cameroon",
    "canada",
    "cape verde",
    "central african republic",
    "chad",
    "chile",
    "china",
    "colombia",
    "costa rica",
    "croatia",
    "cuba",
    "cyprus",
    "czech republic",
    "czechia",
    "democratic republic of the congo",
    "denmark",
    "dominican republic",
    "ecuador",
    "egypt",
    "el salvador",
    "emea",
    "england",
    "estonia",
    "ethiopia",
    "europe",
    "european union",
    "fiji",
    "finland",
    "france",
    "gabon",
    "gambia",
    "germany",
    "ghana",
    "greece",
    "guatemala",
    "guinea",
    "guyana",
    "haiti",
    "honduras",
    "hong kong",
    "hungary",
    "iceland",
    "ie",
    "india",
    "indonesia",
    "iran",
    "iraq",
    "ireland",
    "israel",
    "italy",
    "jamaica",
    "japan",
    "jordan",
    "kazakhstan",
    "kenya",
    "korea",
    "kuwait",
    "kyrgyzstan",
    "laos",
    "latin america",
    "latam",
    "latvia",
    "lebanon",
    "liberia",
    "libya",
    "liechtenstein",
    "lithuania",
    "luxembourg",
    "madagascar",
    "malawi",
    "malaysia",
    "maldives",
    "mali",
    "malta",
    "mauritania",
    "mauritius",
    "mexico",
    "méxico",
    "middle east",
    "moldova",
    "monaco",
    "mongolia",
    "montenegro",
    "morocco",
    "mozambique",
    "myanmar",
    "namibia",
    "nepal",
    "netherlands",
    "new zealand",
    "nicaragua",
    "niger",
    "nigeria",
    "north korea",
    "north macedonia",
    "norway",
    "oman",
    "pakistan",
    "palestine",
    "panama",
    "papua new guinea",
    "paraguay",
    "peru",
    "philippines",
    "poland",
    "portugal",
    "qatar",
    "quebec",
    "québec",
    "republic of the congo",
    "romania",
    "russia",
    "rwanda",
    "saudi arabia",
    "scotland",
    "senegal",
    "serbia",
    "seychelles",
    "sierra leone",
    "singapore",
    "slovakia",
    "slovenia",
    "somalia",
    "south africa",
    "south korea",
    "spain",
    "sri lanka",
    "sudan",
    "suriname",
    "sweden",
    "switzerland",
    "syria",
    "taiwan",
    "tajikistan",
    "tanzania",
    "thailand",
    "togo",
    "trinidad and tobago",
    "tunisia",
    "turkey",
    "turkmenistan",
    "u.k.",
    "uganda",
    "uk",
    "ukraine",
    "united arab emirates",
    "united kingdom",
    "uruguay",
    "uzbekistan",
    "venezuela",
    "vietnam",
    "wales",
    "yemen",
    "zambia",
    "zimbabwe",
}

US_COUNTRY_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:united states(?: of america)?|u\.?s\.?(?:a\.?)?)(?![A-Za-z])",
    re.IGNORECASE,
)
US_STATE_NAME_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:"
    + "|".join(
        re.escape(name)
        for name in sorted(US_STATE_NAMES, key=len, reverse=True)
    )
    + r")(?![A-Za-z])",
    re.IGNORECASE,
)
US_STATE_ABBREVIATION_PATTERN = re.compile(
    r"(?:^|[,;/|·(\s-])(?:"
    + "|".join(sorted(US_STATE_ABBREVIATIONS))
    + r")(?:\s+\d{5}(?:-\d{4})?)?(?=$|[,;/|·)\s-])"
)
NON_US_LOCATION_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:"
    + "|".join(
        re.escape(name)
        for name in sorted(NON_US_LOCATION_TERMS, key=len, reverse=True)
    )
    + r")(?![A-Za-z])",
    re.IGNORECASE,
)
REMOTE_ONLY_LOCATION_PATTERN = re.compile(
    r"^(?:(?:fully|100%)\s+)?remote"
    r"(?:\s*(?:[-–—,/|·()]|\b(?:position|role|work|anywhere|worldwide|global)\b)\s*)*$",
    re.IGNORECASE,
)


def us_location_decision(
    location: str | None,
    *,
    country: str | None = None,
    is_remote: bool = False,
) -> bool | None:
    """
    Return True for a known U.S. location, False for a known non-U.S.
    location, and None when a city-only location needs Ollama classification.

    A remote job with no geographic restriction is accepted. A blank or
    ambiguous non-remote location is not accepted without model confirmation.
    """

    location_text = str(location or "").strip()
    country_text = str(country or "").strip()
    if country_text:
        return bool(US_COUNTRY_PATTERN.search(country_text))

    if US_COUNTRY_PATTERN.search(location_text):
        return True

    if US_STATE_NAME_PATTERN.search(location_text):
        return True

    if US_STATE_ABBREVIATION_PATTERN.search(location_text):
        return True

    if NON_US_LOCATION_PATTERN.search(location_text):
        return False

    if location_text and REMOTE_ONLY_LOCATION_PATTERN.fullmatch(location_text):
        return True

    if is_remote and not location_text:
        return True

    return None


def job_us_location_decision(job: dict) -> bool | None:
    return us_location_decision(
        job.get("location"),
        country=job.get("_location_country"),
        is_remote=bool(job.get("_is_remote")),
    )


def stored_job_is_us_eligible(job: dict) -> bool:
    decision = job_us_location_decision(job)

    if decision is not None:
        return decision

    analysis = job.get("analysis")

    return (
        isinstance(analysis, dict)
        and str(
            analysis.get("us_location_eligible") or ""
        ).strip().upper() == "YES"
    )


# ============================================================
# HTTP HELPERS
# ============================================================

def classify_provider_error(
    error: Exception,
    ats: str,
) -> tuple[str, str]:
    normalized_ats = str(ats or "").strip().lower()
    provider_label = normalized_ats.replace("-", " ").replace("_", " ")
    provider_name = (
        provider_label.title()
        if provider_label
        else "Provider"
    )

    if isinstance(error, requests.HTTPError):
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)

        if status_code == 404:
            if normalized_ats == "greenhouse":
                return (
                    "missing_resource",
                    "Greenhouse board is unavailable",
                )
            if normalized_ats == "workable":
                return (
                    "missing_resource",
                    "Workable board is unavailable",
                )
            return (
                "missing_resource",
                f"{provider_name} resource is unavailable",
            )

        if status_code == 429:
            if normalized_ats == "workable":
                return (
                    "rate_limited",
                    "Workable is rate limiting requests",
                )
            return (
                "rate_limited",
                f"{provider_name} is rate limiting requests",
            )

        if status_code in {500, 502, 503, 504}:
            return (
                "transient_error",
                f"{provider_name} returned a transient server error",
            )

    if isinstance(error, requests.Timeout):
        return (
            "timeout",
            f"{provider_name} request timed out",
        )

    if isinstance(error, requests.ConnectionError):
        return (
            "connection_error",
            f"{provider_name} connection failed",
        )

    if isinstance(error, ValueError):
        return (
            "invalid_response",
            f"{provider_name} returned an invalid response",
        )

    return (
        "unexpected_error",
        f"{provider_name} request failed: {error}",
    )


def create_session() -> requests.Session:
    session = requests.Session()

    retries = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(
        max_retries=retries,
        pool_connections=FETCH_WORKERS,
        pool_maxsize=FETCH_WORKERS,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "ATSift/3.0 (local job discovery)",
        }
    )

    return session


def get_thread_session() -> requests.Session:
    session = getattr(session_local, "session", None)

    if session is None:
        session = create_session()
        session_local.session = session

    return session


def get_json_value(
    session: requests.Session,
    url: str,
    params: dict | None = None,
):
    response = session.get(
        url,
        params=params,
        timeout=TIMEOUT,
    )

    response.raise_for_status()
    return response.json()


def get_json(
    session: requests.Session,
    url: str,
    params: dict | None = None,
) -> dict:
    data = get_json_value(
        session,
        url,
        params=params,
    )

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object from {url}"
        )

    return data


def get_json_list(
    session: requests.Session,
    url: str,
    params: dict | None = None,
) -> list:
    data = get_json_value(
        session,
        url,
        params=params,
    )

    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array from {url}"
        )

    return data


def post_json(
    session: requests.Session,
    url: str,
    payload: dict,
) -> dict:
    response = session.post(
        url,
        json=payload,
        headers={"Accept-Language": "en-US,en;q=0.9"},
        timeout=TIMEOUT,
    )

    response.raise_for_status()
    data = response.json()

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object from {url}"
        )

    return data


# ============================================================
# OLLAMA ANALYSIS
# ============================================================

def analysis_fingerprint(job: dict) -> str:
    source_text = "|".join(
        [
            ANALYSIS_PROMPT_VERSION,
            OLLAMA_MODEL,
            str(job.get("title") or ""),
            str(job.get("location") or ""),
            str(job.get("team") or ""),
            str(job.get("salary_context") or ""),
            str(job.get("description") or "")[
                :MAX_DESCRIPTION_CHARS
            ],
        ]
    )

    return hashlib.sha256(
        source_text.encode("utf-8")
    ).hexdigest()


def fallback_analysis() -> dict:
    return {
        "us_location_eligible": "UNKNOWN",
        "opt_eligible": "UNKNOWN",
        "opt_blocking_line": (
            "Ollama analysis was unavailable. "
            "Review the job description manually."
        ),
        "degree": "Analysis unavailable.",
        "qualifications": "Analysis unavailable.",
        "eligibility": "Analysis unavailable.",
        "key_tech_skills": [],
        "experience_years": "Analysis unavailable.",
        "minimum_years": None,
        "experience_fit": "UNKNOWN",
        "stop_after_experience": False,
        "ats_keywords": [],
        "tip": "Review the complete job description manually.",
        "salary": "Not listed.",
        "team": "Not listed.",
        "analysis_failed": True,
    }


def normalize_analysis(result: dict) -> dict:
    minimum_years = result.get("minimum_years")

    if isinstance(minimum_years, bool):
        minimum_years = None

    if isinstance(minimum_years, str):
        try:
            minimum_years = float(minimum_years)
        except ValueError:
            minimum_years = None

    if not isinstance(minimum_years, (int, float)):
        minimum_years = None

    stop_after_experience = (
        minimum_years is not None
        and minimum_years >= 4
    )

    if minimum_years is None:
        experience_fit = "UNKNOWN"
    elif stop_after_experience:
        experience_fit = "NO"
    else:
        experience_fit = "YES"

    opt_eligible = str(
        result.get("opt_eligible") or ""
    ).strip().upper()

    if opt_eligible not in {"YES", "NO"}:
        opt_eligible = "UNKNOWN"

    us_location_eligible = str(
        result.get("us_location_eligible") or ""
    ).strip().upper()

    if us_location_eligible not in {"YES", "NO"}:
        us_location_eligible = "UNKNOWN"

    salary = compact_text(
        result.get("salary"),
        default="Not listed.",
        maximum=180,
    )

    if salary.lower() in {
        "not available",
        "not provided",
        "none",
        "unknown",
        "",
    }:
        salary = "Not listed."

    return {
        "us_location_eligible": us_location_eligible,
        "opt_eligible": opt_eligible,
        "opt_blocking_line": compact_text(
            result.get("opt_blocking_line"),
            default="",
            maximum=500,
        ),
        "degree": compact_text(
            result.get("degree"),
            maximum=220,
        ),
        "qualifications": compact_text(
            result.get("qualifications"),
            maximum=260,
        ),
        "eligibility": compact_text(
            result.get("eligibility"),
            maximum=260,
        ),
        "key_tech_skills": compact_list(
            result.get("key_tech_skills"),
            maximum_items=15,
        ),
        "experience_years": compact_text(
            result.get("experience_years"),
            maximum=180,
        ),
        "minimum_years": minimum_years,
        "experience_fit": experience_fit,
        "stop_after_experience": stop_after_experience,
        "ats_keywords": compact_list(
            result.get("ats_keywords"),
            maximum_items=20,
        ),
        "tip": compact_text(
            result.get("tip"),
            maximum=260,
        ),
        "salary": salary,
        "team": compact_text(
            result.get("team"),
            default="Not listed.",
            maximum=160,
        ),
        "analysis_failed": False,
    }


def analyze_job_with_ollama(job: dict) -> dict:
    description = str(
        job.get("description") or ""
    )[:MAX_DESCRIPTION_CHARS]

    source_team = str(
        job.get("team") or ""
    )

    salary_context = str(
        job.get("salary_context") or ""
    )

    prompt = f"""
Analyze this job description for an F-1 OPT job seeker.

This is a JD-only screening check, not legal advice.

JOB INFORMATION

Title:
{job.get("title") or "Not listed"}

Company:
{job.get("company") or "Not listed"}

Location:
{job.get("location") or "Not listed"}

Source team or department:
{source_team or "Not listed"}

Structured compensation data:
{salary_context or "Not listed"}

JOB DESCRIPTION

{description}

RETURN THE ANSWERS IN THIS EXACT LOGICAL ORDER:

1. U.S. Location Eligible?
2. OPT Eligible?
3. Requirements
4. Key Tech and Skills
5. Experience Required?
6. Top ATS Keywords
7. One Tip based on JD
8. Salary
9. Summary team

STRICT RULES

U.S. LOCATION ELIGIBILITY:
- Return YES only when the listed location includes at least one work
  location in the United States.
- Also return YES for a remote job when no country or geographic region is
  stated.
- Return NO when the job is clearly outside the United States or remote work
  is restricted to another country or region.
- For a city-only location, use your geographic knowledge. If the city is
  ambiguous between the United States and another country, return NO unless
  the JD clearly confirms a U.S. work location.
- Do not infer a U.S. location from the company headquarters.

OPT ELIGIBILITY:
- Return NO only when the location is clearly outside the United States,
  or the JD explicitly blocks F-1 OPT candidates.
- Blocking language includes:
  no current or future sponsorship,
  must work without sponsorship,
  US citizen only,
  permanent resident only,
  required US citizenship,
  or a clearance requirement that requires citizenship.
- When returning NO, copy the exact blocking sentence from the JD.
- When the location itself is outside the United States, use the exact
  listed location as the blocking line.
- When no explicit blocker is found, return YES.
- Do not invent sponsorship information.

REQUIREMENTS:
- degree must be one short line.
- qualifications must be one short line.
- eligibility must be one short line.
- State "Not clearly stated." when missing.

SKILLS:
- List only technologies, tools, languages, frameworks, platforms,
  data systems, cloud systems, and important role skills.
- Return 10 to 15 distinct skills when the JD supports that many.
- Never invent, repeat, or pad skills that are not present in the JD.
- No explanations.

EXPERIENCE:
- Extract the minimum required professional experience.
- Ignore preferred experience unless it is also required.
- minimum_years must be a number or null.
- experience_years must quote or closely preserve the JD's concise
  experience requirement, including the number and unit when stated.
- Never infer a number that the JD does not state.
- The application will automatically stop after this question when
  minimum_years is 4 or more.

ATS KEYWORDS:
- Return the top 15 to 20 distinct resume keywords when the JD supports
  that many, including technologies, role competencies, domain terms,
  and important responsibilities.
- Never invent, repeat, or pad keywords that are not present in the JD.
- No explanations.

TIP:
- Give only the single most important role-specific action.
- One short sentence.

SALARY:
- One short line.
- Include the stated range and currency when available.
- Otherwise return exactly: Not listed.

TEAM:
- Use the source team, department, or the best clear team name from the JD.
- Otherwise return exactly: Not listed.

Keep every string short and scannable.
Never write long paragraphs.
Return only JSON matching the supplied schema.
""".strip()

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "format": JOB_ANALYSIS_SCHEMA,
                "stream": False,
                "options": {
                    "temperature": 0,
                },
            },
            timeout=150,
        )

        response.raise_for_status()

        response_data = response.json()

        content = (
            response_data
            .get("message", {})
            .get("content", "")
            .strip()
        )

        parsed = json.loads(content)

        if not isinstance(parsed, dict):
            raise ValueError(
                "Ollama response was not a JSON object"
            )

        return normalize_analysis(parsed)

    except (
        requests.RequestException,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"[warn] Ollama analysis failed for "
            f"'{job.get('title')}': {error}"
        )

        return fallback_analysis()


def get_job_analysis(
    job: dict,
    cache: dict,
) -> dict:
    if not USE_OLLAMA_ANALYSIS:
        return fallback_analysis()

    uid = job["uid"]
    fingerprint = analysis_fingerprint(job)

    cached = cache.get(uid)

    if (
        isinstance(cached, dict)
        and cached.get("fingerprint") == fingerprint
        and isinstance(cached.get("analysis"), dict)
    ):
        return cached["analysis"]

    analysis = analyze_job_with_ollama(job)

    cache[uid] = {
        "fingerprint": fingerprint,
        "analysis": analysis,
        "analyzed_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    return analysis


# ============================================================
# GREENHOUSE
# ============================================================

def fetch_greenhouse(
    session: requests.Session,
    company_name: str,
    slug: str,
    lookback_hours: int,
) -> list[dict]:
    encoded_slug = quote(slug, safe="")
    list_url = (
        "https://boards-api.greenhouse.io/"
        f"v1/boards/{encoded_slug}/jobs?content=true"
    )

    board = get_json(session, list_url)

    results: list[dict] = []

    for summary in board.get("jobs", []):
        title = summary.get("title")

        if not title_matches_keywords(title):
            continue

        source_updated_at = summary.get("updated_at")

        # first_published can never be later than updated_at.
        # Therefore an old updated_at safely eliminates the job.
        if (
            source_updated_at
            and not is_recent(
                source_updated_at,
                lookback_hours,
            )
        ):
            continue

        job_id = summary.get("id")

        if job_id is None:
            continue

        summary_location_data = summary.get("location")
        summary_location = location_name(summary_location_data)
        summary_country = (
            labeled_value(
                summary_location_data.get("country")
            )
            if isinstance(summary_location_data, dict)
            else None
        )

        if us_location_decision(
            summary_location,
            country=summary_country,
        ) is False:
            continue

        detail_url = (
            "https://boards-api.greenhouse.io/"
            f"v1/boards/{encoded_slug}/jobs/{job_id}"
        )

        try:
            detail = get_json(
                session,
                detail_url,
            )

        except (
            requests.RequestException,
            ValueError,
        ) as error:
            classification, summary = classify_provider_error(
                error,
                "greenhouse",
            )
            if classification == "unexpected_error":
                print(
                    f"[warn] Greenhouse detail failed for "
                    f"{company_name} job {job_id}: {summary}"
                )
            continue

        first_published_at = (
            detail.get("first_published")
            or summary.get("first_published")
        )

        if not is_recent(
            first_published_at,
            lookback_hours,
        ):
            continue

        source_updated_at = (
            detail.get("updated_at")
            or source_updated_at
        )

        job_url = (
            detail.get("absolute_url")
            or summary.get("absolute_url")
        )

        team = department_names(
            detail.get("departments")
            or summary.get("departments")
            or []
        )

        description = strip_html(
            detail.get("content")
            or summary.get("content")
        )

        location_data = (
            detail.get("location")
            or summary_location_data
        )
        location = location_name(location_data)
        location_country = (
            labeled_value(location_data.get("country"))
            if isinstance(location_data, dict)
            else None
        )
        is_remote = "remote" in location.casefold()

        record = {
            "uid": f"greenhouse:{slug}:{job_id}",
            "source": "greenhouse",
            "company": company_name,
            "slug": slug,
            "id": str(job_id),
            "title": detail.get("title") or title,
            "location": location,
            "_location_country": location_country,
            "_is_remote": is_remote,
            "team": team,
            "first_published_at": first_published_at,
            "source_updated_at": source_updated_at,
            "job_url": job_url,
            "apply_url": job_url,
            "description": description,
            "salary_context": "",
        }

        if job_us_location_decision(record) is not False:
            results.append(record)

        time.sleep(GREENHOUSE_DETAIL_DELAY_SEC)

    return results


# ============================================================
# ASHBY
# ============================================================

def extract_ashby_job_id(job: dict) -> str | None:
    direct_id = job.get("id")

    if direct_id:
        return str(direct_id)

    job_url = (
        job.get("jobUrl")
        or job.get("applyUrl")
    )

    if not job_url:
        return None

    parts = [
        part
        for part in urlparse(job_url).path.split("/")
        if part
    ]

    if not parts:
        return None

    return parts[-1]


def fetch_ashby(
    session: requests.Session,
    company_name: str,
    slug: str,
    lookback_hours: int,
) -> list[dict]:
    encoded_slug = quote(slug, safe="")
    url = (
        "https://api.ashbyhq.com/"
        f"posting-api/job-board/{encoded_slug}"
        "?includeCompensation=true"
    )

    board = get_json(session, url)

    results: list[dict] = []

    for job in board.get("jobs", []):
        if job.get("isListed") is False:
            continue

        title = job.get("title")

        if not title_matches_keywords(title):
            continue

        first_published_at = job.get("publishedAt")

        if not is_recent(
            first_published_at,
            lookback_hours,
        ):
            continue

        job_id = extract_ashby_job_id(job)

        if not job_id:
            continue

        job_url = (
            job.get("jobUrl")
            or job.get("applyUrl")
        )

        apply_url = (
            job.get("applyUrl")
            or job_url
        )

        description = (
            job.get("descriptionPlain")
            or strip_html(
                job.get("descriptionHtml")
            )
        )

        team = str(
            job.get("team")
            or job.get("department")
            or ""
        ).strip()

        compensation = job.get("compensation")

        if compensation:
            salary_context = json.dumps(
                compensation,
                ensure_ascii=False,
            )
        else:
            salary_context = ""

        location = str(job.get("location") or "").strip()
        is_remote = (
            bool(job.get("isRemote"))
            or str(job.get("workplaceType") or "").casefold()
            == "remote"
            or "remote" in location.casefold()
        )

        if is_remote and "remote" not in location.casefold():
            location = (
                f"{location} · Remote"
                if location
                else "Remote"
            )

        record = {
            "uid": f"ashby:{slug}:{job_id}",
            "source": "ashby",
            "company": company_name,
            "slug": slug,
            "id": job_id,
            "title": title,
            "location": location,
            "_location_country": labeled_value(
                job.get("country")
            ),
            "_is_remote": is_remote,
            "team": team,
            "first_published_at": first_published_at,
            "source_updated_at": None,
            "job_url": job_url,
            "apply_url": apply_url,
            "description": str(description or ""),
            "salary_context": salary_context,
        }

        if job_us_location_decision(record) is not False:
            results.append(record)

    return results


# ============================================================
# LEVER
# ============================================================

LEVER_API_BASES = (
    "https://api.lever.co/v0/postings",
    "https://api.eu.lever.co/v0/postings",
)


def lever_job_record(
    job: dict,
    company_name: str,
    slug: str,
    lookback_hours: int,
) -> dict | None:
    title = str(job.get("text") or "").strip()

    if not title_matches_keywords(title):
        return None

    first_published_at = unix_milliseconds_to_iso(
        job.get("createdAt")
    )

    if not is_recent(first_published_at, lookback_hours):
        return None

    job_id = str(job.get("id") or "").strip()

    if not job_id:
        return None

    categories = job.get("categories")

    if not isinstance(categories, dict):
        categories = {}

    all_locations = categories.get("allLocations")

    if isinstance(all_locations, list):
        location = " · ".join(
            str(item).strip()
            for item in all_locations
            if str(item).strip()
        )
    else:
        location = ""

    location = (
        location
        or str(categories.get("location") or "").strip()
        or (
            "Remote"
            if str(job.get("workplaceType") or "").lower()
            == "remote"
            else ""
        )
    )
    is_remote = (
        str(job.get("workplaceType") or "").casefold()
        == "remote"
        or "remote" in location.casefold()
    )

    lists = job.get("lists")
    list_sections: list[str] = []

    if isinstance(lists, list):
        for section in lists:
            if not isinstance(section, dict):
                continue

            heading = str(section.get("text") or "").strip()
            content = strip_html(section.get("content"))
            list_sections.append(
                join_text_parts([heading, content])
            )

    description = join_text_parts(
        [
            job.get("descriptionPlain"),
            *list_sections,
            job.get("additionalPlain"),
        ]
    )

    job_url = str(job.get("hostedUrl") or "").strip()
    apply_url = str(
        job.get("applyUrl")
        or job_url
    ).strip()

    record = {
        "uid": f"lever:{slug}:{job_id}",
        "source": "lever",
        "company": company_name,
        "slug": slug,
        "id": job_id,
        "title": title,
        "location": location,
        "_location_country": labeled_value(
            categories.get("country")
        ),
        "_is_remote": is_remote,
        "team": str(
            categories.get("team")
            or categories.get("department")
            or ""
        ).strip(),
        "first_published_at": first_published_at,
        "source_updated_at": None,
        "job_url": job_url,
        "apply_url": apply_url,
        "description": description,
        "salary_context": "",
    }

    if job_us_location_decision(record) is False:
        return None

    return record


def fetch_lever(
    session: requests.Session,
    company_name: str,
    slug: str,
    lookback_hours: int,
) -> list[dict]:
    encoded_slug = quote(slug, safe="")
    last_not_found: requests.HTTPError | None = None

    for base_url in LEVER_API_BASES:
        results: list[dict] = []
        skip = 0

        while True:
            url = f"{base_url}/{encoded_slug}"

            try:
                page = get_json_list(
                    session,
                    url,
                    params={
                        "mode": "json",
                        "skip": skip,
                        "limit": ATS_PAGE_SIZE,
                    },
                )
            except requests.HTTPError as error:
                if (
                    skip == 0
                    and error.response is not None
                    and error.response.status_code == 404
                ):
                    last_not_found = error
                    break

                raise

            for job in page:
                if not isinstance(job, dict):
                    continue

                record = lever_job_record(
                    job,
                    company_name,
                    slug,
                    lookback_hours,
                )

                if record:
                    results.append(record)

            if len(page) < ATS_PAGE_SIZE:
                return results

            skip += len(page)

    if last_not_found:
        raise last_not_found

    return []


# ============================================================
# SMARTRECRUITERS
# ============================================================

def smartrecruiters_description(job: dict) -> str:
    job_ad = job.get("jobAd")

    if not isinstance(job_ad, dict):
        return ""

    sections = job_ad.get("sections")

    if not isinstance(sections, dict):
        return ""

    section_order = (
        "jobDescription",
        "qualifications",
        "additionalInformation",
        "companyDescription",
    )
    parts: list[str] = []

    for key in section_order:
        section = sections.get(key)

        if not isinstance(section, dict):
            continue

        title = str(section.get("title") or "").strip()
        text = strip_html(section.get("text"))

        if text:
            parts.append(join_text_parts([title, text]))

    return join_text_parts(parts)


def smartrecruiters_job_record(
    job: dict,
    company_name: str,
    slug: str,
    lookback_hours: int,
) -> dict | None:
    if job.get("active") is False:
        return None

    title = str(job.get("name") or "").strip()

    if not title_matches_keywords(title):
        return None

    first_published_at = str(
        job.get("releasedDate") or ""
    ).strip()

    if not is_recent(first_published_at, lookback_hours):
        return None

    job_id = str(
        job.get("id")
        or job.get("uuid")
        or ""
    ).strip()

    if not job_id:
        return None

    location_data = job.get("location")

    if not isinstance(location_data, dict):
        location_data = {}

    location = str(
        location_data.get("fullLocation") or ""
    ).strip()

    if not location:
        location = location_parts(
            location_data.get("city"),
            location_data.get("region"),
            location_data.get("country"),
        )

    work_style = ""

    if location_data.get("remote"):
        work_style = "Remote"
    elif location_data.get("hybrid"):
        work_style = "Hybrid"

    if work_style and work_style.lower() not in location.lower():
        location = (
            f"{location} · {work_style}"
            if location
            else work_style
        )

    is_remote = bool(location_data.get("remote"))

    job_url = str(
        job.get("postingUrl")
        or job.get("applyUrl")
        or ""
    ).strip()
    apply_url = str(
        job.get("applyUrl")
        or job_url
    ).strip()

    compensation = job.get("compensation")
    salary_context = (
        json.dumps(compensation, ensure_ascii=False)
        if compensation
        else ""
    )

    record = {
        "uid": f"smartrecruiters:{slug}:{job_id}",
        "source": "smartrecruiters",
        "company": company_name,
        "slug": slug,
        "id": job_id,
        "title": title,
        "location": location,
        "_location_country": labeled_value(
            location_data.get("country")
        ),
        "_is_remote": is_remote,
        "team": (
            labeled_value(job.get("department"))
            or labeled_value(job.get("function"))
        ),
        "first_published_at": first_published_at,
        "source_updated_at": None,
        "job_url": job_url,
        "apply_url": apply_url,
        "description": smartrecruiters_description(job),
        "salary_context": salary_context,
    }

    if job_us_location_decision(record) is False:
        return None

    return record


def fetch_smartrecruiters(
    session: requests.Session,
    company_name: str,
    slug: str,
    lookback_hours: int,
) -> list[dict]:
    encoded_slug = quote(slug, safe="")
    list_url = (
        "https://api.smartrecruiters.com/v1/companies/"
        f"{encoded_slug}/postings"
    )
    offset = 0
    results: list[dict] = []

    while True:
        page = get_json(
            session,
            list_url,
            params={
                "limit": ATS_PAGE_SIZE,
                "offset": offset,
                "destination": "PUBLIC",
                "releasedAfter": lookback_cutoff_iso(
                    lookback_hours
                ),
            },
        )
        content = page.get("content")

        if not isinstance(content, list):
            raise ValueError(
                "SmartRecruiters response is missing content"
            )

        for summary in content:
            if not isinstance(summary, dict):
                continue

            title = str(summary.get("name") or "").strip()
            released_at = str(
                summary.get("releasedDate") or ""
            ).strip()

            if (
                not title_matches_keywords(title)
                or not is_recent(released_at, lookback_hours)
            ):
                continue

            posting_id = str(
                summary.get("id")
                or summary.get("uuid")
                or ""
            ).strip()

            if not posting_id:
                continue

            detail_url = (
                f"{list_url}/{quote(posting_id, safe='')}"
            )

            try:
                detail = get_json(session, detail_url)
            except (
                requests.RequestException,
                ValueError,
            ) as error:
                classification, summary = classify_provider_error(
                    error,
                    "smartrecruiters",
                )
                if classification == "unexpected_error":
                    print(
                        f"[warn] SmartRecruiters detail failed for "
                        f"{company_name} posting {posting_id}: {summary}"
                    )
                continue

            record = smartrecruiters_job_record(
                detail,
                company_name,
                slug,
                lookback_hours,
            )

            if record:
                results.append(record)

        total_found = int(page.get("totalFound") or 0)
        offset += len(content)

        if (
            not content
            or len(content) < ATS_PAGE_SIZE
            or offset >= total_found
        ):
            break

    return results


# ============================================================
# WORKABLE
# ============================================================

def workable_job_record(
    job: dict,
    company_name: str,
    slug: str,
    lookback_hours: int,
) -> dict | None:
    title = str(job.get("title") or "").strip()

    if not title_matches_keywords(title):
        return None

    first_published_at = str(
        job.get("published_on")
        or job.get("created_at")
        or ""
    ).strip()

    if not is_recent(first_published_at, lookback_hours):
        return None

    job_id = str(
        job.get("shortcode")
        or job.get("code")
        or ""
    ).strip()

    if not job_id:
        return None

    location = location_parts(
        job.get("city"),
        job.get("state"),
        job.get("country"),
    )

    is_remote = (
        bool(job.get("telecommuting"))
        or str(job.get("workplace_type") or "").lower()
        == "remote"
    )

    if is_remote and "remote" not in location.lower():
        location = (
            f"{location} · Remote"
            if location
            else "Remote"
        )

    job_url = str(
        job.get("url")
        or job.get("shortlink")
        or ""
    ).strip()
    apply_url = str(
        job.get("application_url")
        or job_url
    ).strip()

    record = {
        "uid": f"workable:{slug}:{job_id}",
        "source": "workable",
        "company": company_name,
        "slug": slug,
        "id": job_id,
        "title": title,
        "location": location,
        "_location_country": labeled_value(
            job.get("country")
        ),
        "_is_remote": is_remote,
        "team": str(
            job.get("department")
            or job.get("function")
            or ""
        ).strip(),
        "first_published_at": first_published_at,
        "source_updated_at": None,
        "job_url": job_url,
        "apply_url": apply_url,
        "description": strip_html(job.get("description")),
        "salary_context": "",
    }

    if job_us_location_decision(record) is False:
        return None

    return record


def fetch_workable(
    session: requests.Session,
    company_name: str,
    slug: str,
    lookback_hours: int,
) -> list[dict]:
    encoded_slug = quote(slug, safe="")
    url = (
        "https://www.workable.com/api/accounts/"
        f"{encoded_slug}"
    )
    board = get_json(
        session,
        url,
        params={"details": "true"},
    )
    jobs = board.get("jobs")

    if not isinstance(jobs, list):
        raise ValueError(
            "Workable response is missing jobs"
        )

    results: list[dict] = []

    for job in jobs:
        if not isinstance(job, dict):
            continue

        record = workable_job_record(
            job,
            company_name,
            slug,
            lookback_hours,
        )

        if record:
            results.append(record)

    return results


# ============================================================
# WORKDAY
# ============================================================

WORKDAY_HOST_PATTERN = re.compile(
    r"^(?P<tenant>[a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com$",
    re.IGNORECASE,
)


def workday_site_config(slug: str) -> dict[str, str]:
    parsed = urlparse(slug.strip())
    hostname = str(parsed.hostname or "").lower()
    host_match = WORKDAY_HOST_PATTERN.fullmatch(hostname)
    path_parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if (
        parsed.scheme != "https"
        or not host_match
        or not path_parts
    ):
        raise ValueError(
            "Workday slug must be an HTTPS myworkdayjobs "
            "career-site URL"
        )

    tenant = host_match.group("tenant")
    site = path_parts[0]
    encoded_tenant = quote(tenant, safe="")
    encoded_site = quote(site, safe="%")
    origin = f"https://{hostname}"

    return {
        "tenant": tenant,
        "site": site,
        "public_url": f"{origin}/{encoded_site}",
        "cxs_url": (
            f"{origin}/wday/cxs/"
            f"{encoded_tenant}/{encoded_site}"
        ),
    }


def workday_posted_date(
    value: str | None,
    *,
    now: datetime | None = None,
) -> str | None:
    text = str(value or "").strip().casefold()

    if not text:
        return None

    reference = now or datetime.now(timezone.utc)

    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    if "today" in text:
        age = timedelta(0)
    elif "yesterday" in text:
        age = timedelta(days=1)
    else:
        age_match = re.search(
            r"(\d+)\+?\s+"
            r"(minute|hour|day|week)s?\s+ago",
            text,
        )

        if not age_match:
            return None

        amount = int(age_match.group(1))
        unit = age_match.group(2)

        if unit == "minute":
            age = timedelta(minutes=amount)
        elif unit == "hour":
            age = timedelta(hours=amount)
        elif unit == "week":
            age = timedelta(weeks=amount)
        else:
            age = timedelta(days=amount)

    return (reference - age).date().isoformat()


def workday_job_record(
    payload: dict,
    summary: dict,
    company_name: str,
    slug: str,
    lookback_hours: int,
    *,
    site_config: dict[str, str] | None = None,
) -> dict | None:
    info = payload.get("jobPostingInfo")

    if not isinstance(info, dict):
        return None

    if (
        info.get("canApply") is False
        or info.get("posted") is False
    ):
        return None

    title = str(
        info.get("title")
        or summary.get("title")
        or ""
    ).strip()

    if not title_matches_keywords(title):
        return None

    first_published_at = str(
        info.get("startDate") or ""
    ).strip()

    if not first_published_at:
        first_published_at = str(
            workday_posted_date(
                info.get("postedOn")
                or summary.get("postedOn")
            )
            or ""
        )

    if not is_recent(first_published_at, lookback_hours):
        return None

    config = site_config or workday_site_config(slug)
    external_path = str(
        summary.get("externalPath") or ""
    ).strip()

    if external_path and not external_path.startswith("/"):
        external_path = f"/{external_path}"

    bullet_fields = summary.get("bulletFields")
    summary_id = ""

    if isinstance(bullet_fields, list) and bullet_fields:
        summary_id = str(bullet_fields[0] or "").strip()

    job_id = str(
        info.get("jobReqId")
        or info.get("jobPostingId")
        or info.get("id")
        or summary_id
        or external_path.rsplit("/", 1)[-1]
        or ""
    ).strip()

    if not job_id:
        return None

    location_data = info.get("jobRequisitionLocation")

    if not isinstance(location_data, dict):
        location_data = {}

    location = str(
        info.get("location")
        or location_data.get("descriptor")
        or summary.get("locationsText")
        or ""
    ).strip()
    country_data = (
        location_data.get("country")
        or info.get("country")
    )
    country = labeled_value(country_data)

    if (
        not country
        and isinstance(country_data, dict)
        and str(country_data.get("alpha2Code") or "").upper()
        == "US"
    ):
        country = "United States"

    is_remote = "remote" in location.casefold()
    public_job_url = (
        f"{config['public_url']}{external_path}"
        if external_path
        else config["public_url"]
    )
    job_url = str(
        info.get("externalUrl")
        or public_job_url
    ).strip()
    hiring_organization = payload.get("hiringOrganization")
    team = (
        str(hiring_organization.get("name") or "").strip()
        if isinstance(hiring_organization, dict)
        else ""
    )

    record = {
        "uid": (
            f"workday:{config['tenant']}:"
            f"{config['site']}:{job_id}"
        ),
        "source": "workday",
        "company": company_name,
        "slug": slug,
        "id": job_id,
        "title": title,
        "location": location,
        "_location_country": country,
        "_is_remote": is_remote,
        "team": team,
        "first_published_at": first_published_at,
        "source_updated_at": None,
        "job_url": job_url,
        "apply_url": job_url,
        "description": strip_html(
            info.get("jobDescription")
        ),
        "salary_context": "",
    }

    if job_us_location_decision(record) is False:
        return None

    return record


def fetch_workday(
    session: requests.Session,
    company_name: str,
    slug: str,
    lookback_hours: int,
) -> list[dict]:
    config = workday_site_config(slug)
    list_url = f"{config['cxs_url']}/jobs"
    offset = 0
    results: list[dict] = []

    while True:
        page = post_json(
            session,
            list_url,
            {
                "appliedFacets": {},
                "limit": WORKDAY_PAGE_SIZE,
                "offset": offset,
                "searchText": "",
            },
        )
        postings = page.get("jobPostings")

        if not isinstance(postings, list):
            raise ValueError(
                "Workday response is missing jobPostings"
            )

        for summary in postings:
            if not isinstance(summary, dict):
                continue

            summary_date = workday_posted_date(
                summary.get("postedOn")
            )

            if (
                summary_date
                and not is_recent(
                    summary_date,
                    lookback_hours,
                )
            ):
                continue

            title = str(summary.get("title") or "").strip()

            if not title_matches_keywords(title):
                continue

            external_path = str(
                summary.get("externalPath") or ""
            ).strip()

            if not external_path:
                continue

            if not external_path.startswith("/"):
                external_path = f"/{external_path}"

            detail_url = f"{config['cxs_url']}{external_path}"

            try:
                detail = get_json(session, detail_url)
            except (
                requests.RequestException,
                ValueError,
            ) as error:
                classification, summary = classify_provider_error(
                    error,
                    "workday",
                )
                if classification == "unexpected_error":
                    print(
                        f"[warn] Workday detail failed for "
                        f"{company_name} posting "
                        f"{external_path}: {summary}"
                    )
                continue

            record = workday_job_record(
                detail,
                summary,
                company_name,
                slug,
                lookback_hours,
                site_config=config,
            )

            if record:
                results.append(record)

        offset += len(postings)
        total = int(page.get("total") or 0)
        last_posted_date = (
            workday_posted_date(
                postings[-1].get("postedOn")
            )
            if postings and isinstance(postings[-1], dict)
            else None
        )

        if (
            not postings
            or offset >= total
            or len(postings) < WORKDAY_PAGE_SIZE
            or (
                last_posted_date
                and not is_recent(
                    last_posted_date,
                    lookback_hours,
                )
            )
        ):
            break

    return results


ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "ashby": fetch_ashby,
    "lever": fetch_lever,
    "smartrecruiters": fetch_smartrecruiters,
    "workable": fetch_workable,
    "workday": fetch_workday,
}


def fetch_company_jobs(company: dict) -> list[dict]:
    ats = company["ats"]
    fetcher = ATS_FETCHERS.get(ats)

    if fetcher is None:
        raise ValueError(f"Unsupported ATS '{ats}'")

    jobs = fetcher(
        session=get_thread_session(),
        company_name=company["name"],
        slug=company["slug"],
        lookback_hours=company["lookback_hours"],
    )

    return [
        job
        for job in jobs
        if job_us_location_decision(job) is not False
    ]


def interleave_companies(
    companies: list[dict],
) -> list[dict]:
    buckets = {
        ats: deque()
        for ats in SUPPORTED_ATS
    }

    for company in companies:
        buckets[company["ats"]].append(company)

    ordered: list[dict] = []

    while any(buckets.values()):
        for ats in SUPPORTED_ATS:
            if buckets[ats]:
                ordered.append(buckets[ats].popleft())

    return ordered


# ============================================================
# SCAN STATUS
# ============================================================

def default_status() -> dict:
    return {
        "running": False,
        "message": "Ready to scan",
        "current": 0,
        "total": 0,
        "last_scan_at": None,
        "new_jobs": 0,
        "visible_jobs": 0,
        "errors": 0,
        "lookback_hours": DEFAULT_LOOKBACK_HOURS,
        "dataset": DEFAULT_COMPANY_DATASET,
    }


SCAN_STATUS = load_json(
    SCAN_STATUS_PATH,
    default_status(),
)

if not isinstance(SCAN_STATUS, dict):
    SCAN_STATUS = default_status()

SCAN_STATUS["running"] = False
SCAN_STATUS["message"] = "Ready to scan"

if (
    SCAN_STATUS.get("lookback_hours")
    not in ALLOWED_LOOKBACK_HOURS
):
    SCAN_STATUS["lookback_hours"] = (
        DEFAULT_LOOKBACK_HOURS
    )

if SCAN_STATUS.get("dataset") not in COMPANY_DATASETS:
    SCAN_STATUS["dataset"] = DEFAULT_COMPANY_DATASET


def update_status(**changes) -> None:
    with status_lock:
        SCAN_STATUS.update(changes)


def snapshot_status() -> dict:
    with status_lock:
        return dict(SCAN_STATUS)


# ============================================================
# JOB STORAGE
# ============================================================

def load_stored_jobs() -> list[dict]:
    jobs = load_json(
        JOBS_STORE_PATH,
        [],
    )

    if not isinstance(jobs, list):
        return []

    return deduplicate_jobs(
        [
            job
            for job in jobs
            if isinstance(job, dict)
        ]
    )


def load_visible_jobs(
    lookback_hours: int,
    dataset: str = DEFAULT_COMPANY_DATASET,
) -> list[dict]:
    company_keys = company_keys_for_path(
        COMPANY_DATASET_PATHS[dataset]
    )

    return [
        job
        for job in load_stored_jobs()
        if (
            (
                str(job.get("source") or "").casefold(),
                str(job.get("slug") or "").casefold(),
            )
            in company_keys
            and stored_job_is_us_eligible(job)
            and title_matches_keywords(
                str(job.get("title") or "")
            )
            and is_recent(
                job.get("first_published_at"),
                lookback_hours,
            )
        )
    ]


def snapshot_viewed_jobs() -> dict[str, str]:
    """Return the durable first-viewed timestamp for each job UID."""

    with viewed_jobs_lock:
        viewed_jobs = load_json(
            VIEWED_JOBS_PATH,
            {},
        )

    if not isinstance(viewed_jobs, dict):
        return {}

    normalized: dict[str, str] = {}

    for uid, viewed_at in viewed_jobs.items():
        if not uid or not viewed_at:
            continue

        canonical_uid = canonical_job_uid(str(uid))
        timestamp = str(viewed_at)
        previous = normalized.get(canonical_uid)

        if previous is None or timestamp < previous:
            normalized[canonical_uid] = timestamp

    return normalized


def mark_job_viewed(uid: str) -> str:
    """Persist and return a job's first-viewed timestamp."""

    with viewed_jobs_lock:
        viewed_jobs = load_json(
            VIEWED_JOBS_PATH,
            {},
        )

        if not isinstance(viewed_jobs, dict):
            viewed_jobs = {}

        canonical_uid = canonical_job_uid(uid)
        matching_timestamps = [
            str(timestamp)
            for stored_uid, timestamp in viewed_jobs.items()
            if (
                timestamp
                and canonical_job_uid(str(stored_uid))
                == canonical_uid
            )
        ]
        viewed_at = (
            min(matching_timestamps)
            if matching_timestamps
            else ""
        )

        if not viewed_at:
            viewed_at = datetime.now(timezone.utc).isoformat()
            viewed_jobs[canonical_uid] = viewed_at
            save_json_atomic(
                VIEWED_JOBS_PATH,
                viewed_jobs,
            )

    return viewed_at


# ============================================================
# SCANNER
# ============================================================

def scan_jobs(
    lookback_hours: int,
    dataset: str = DEFAULT_COMPANY_DATASET,
) -> dict:
    dataset_path = COMPANY_DATASET_PATHS[dataset]
    companies = load_companies(dataset_path)
    company_keys = company_keys_for_path(
        dataset_path
    )

    existing_jobs = load_stored_jobs()

    jobs_by_identity = {
        identity: job
        for job in existing_jobs
        if (identity := job_identity(job)) is not None
    }

    analysis_cache = load_json(
        ANALYSIS_CACHE_PATH,
        {},
    )

    if not isinstance(analysis_cache, dict):
        analysis_cache = {}

    scan_started_at = datetime.now(
        timezone.utc
    ).isoformat()

    new_count = 0
    errors = 0

    update_status(
        running=True,
        message=(
            f"Starting {lookback_hours}-hour scan…"
        ),
        current=0,
        total=len(companies),
        new_jobs=0,
        errors=0,
        lookback_hours=lookback_hours,
        dataset=dataset,
    )

    scan_companies = [
        {
            **company,
            "lookback_hours": lookback_hours,
        }
        for company in companies
    ]
    ordered_companies = interleave_companies(
        scan_companies
    )
    candidate_jobs_by_identity: dict[str, dict] = {}

    with ThreadPoolExecutor(
        max_workers=FETCH_WORKERS,
        thread_name_prefix="ats-fetch",
    ) as executor:
        future_companies = {
            executor.submit(
                fetch_company_jobs,
                company,
            ): company
            for company in ordered_companies
        }

        for completed, future in enumerate(
            as_completed(future_companies),
            start=1,
        ):
            company = future_companies[future]

            try:
                jobs = future.result()
            except Exception as error:
                errors += 1
                classification, summary = classify_provider_error(
                    error,
                    company["ats"],
                )

                if classification == "unexpected_error":
                    print(
                        f"[warn] Failed to fetch "
                        f"{company['name']} "
                        f"({company['ats']}): {summary}"
                    )
            else:
                for job in jobs:
                    categories = title_categories(
                        str(job.get("title") or "")
                    )
                    identity = job_identity(job)

                    if identity and categories:
                        job["categories"] = categories
                        candidate_jobs_by_identity[identity] = job

            update_status(
                current=completed,
                message=(
                    f"Searched {completed:,} of "
                    f"{len(companies):,} companies"
                ),
                errors=errors,
                new_jobs=new_count,
            )

    candidate_jobs = sorted(
        candidate_jobs_by_identity.values(),
        key=lambda job: (
            parse_iso_datetime(
                job.get("first_published_at")
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True,
    )

    for index, job in enumerate(candidate_jobs, start=1):
        update_status(
            message=(
                f"Analyzing {index:,} of "
                f"{len(candidate_jobs):,} matched jobs"
            ),
            errors=errors,
            new_jobs=new_count,
        )

        identity = job_identity(job)

        if identity is None:
            continue

        uid = job["uid"]
        previous = jobs_by_identity.get(identity)

        location_decision = job_us_location_decision(job)

        if location_decision is False:
            continue

        analysis = get_job_analysis(
            job,
            analysis_cache,
        )

        if location_decision is None:
            if (
                analysis.get("us_location_eligible")
                != "YES"
            ):
                continue
        else:
            analysis["us_location_eligible"] = "YES"

        now_iso = datetime.now(
            timezone.utc
        ).isoformat()

        if previous is None:
            new_count += 1

        display_job = {
            key: value
            for key, value in job.items()
            if key not in {
                "_is_remote",
                "_location_country",
                "description",
                "salary_context",
            }
        }

        display_job.update(
            {
                "analysis": analysis,
                "discovered_at": (
                    previous.get("discovered_at")
                    if previous
                    else now_iso
                ),
                "last_seen_at": now_iso,
            }
        )

        jobs_by_identity[identity] = display_job

    # Keep a maximum of 72 hours of U.S.-eligible jobs in storage.
    # The selected dropdown value controls what appears in the UI.
    stored_jobs = [
        job
        for job in jobs_by_identity.values()
        if (
            stored_job_is_us_eligible(job)
            and title_matches_keywords(
                str(job.get("title") or "")
            )
            and is_recent(
                job.get("first_published_at"),
                MAX_STORED_HOURS,
            )
        )
    ]

    stored_jobs.sort(
        key=lambda job: (
            parse_iso_datetime(
                job.get("first_published_at")
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True,
    )

    visible_jobs = [
        job
        for job in stored_jobs
        if (
            (
                str(job.get("source") or "").casefold(),
                str(job.get("slug") or "").casefold(),
            )
            in company_keys
            and stored_job_is_us_eligible(job)
            and is_recent(
                job.get("first_published_at"),
                lookback_hours,
            )
        )
    ]

    save_json_atomic(
        JOBS_STORE_PATH,
        stored_jobs,
    )

    save_json_atomic(
        ANALYSIS_CACHE_PATH,
        analysis_cache,
    )

    final_status = {
        "running": False,
        "message": (
            f"Scan complete. {new_count} new "
            f"job{'s' if new_count != 1 else ''} found "
            f"in the last {lookback_hours} hour"
            f"{'' if lookback_hours == 1 else 's'}."
        ),
        "current": len(companies),
        "total": len(companies),
        "last_scan_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "scan_started_at": scan_started_at,
        "new_jobs": new_count,
        "visible_jobs": len(visible_jobs),
        "errors": errors,
        "lookback_hours": lookback_hours,
        "dataset": dataset,
    }

    update_status(**final_status)

    save_json_atomic(
        SCAN_STATUS_PATH,
        final_status,
    )

    return final_status


def scan_worker(
    lookback_hours: int,
    dataset: str = DEFAULT_COMPANY_DATASET,
) -> None:
    try:
        scan_jobs(lookback_hours, dataset)

    except Exception as error:
        print(
            f"[error] Scan crashed: {error}"
        )

        failed_status = snapshot_status()

        failed_status.update(
            {
                "running": False,
                "message": f"Scan failed: {error}",
                "last_scan_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "lookback_hours": lookback_hours,
                "dataset": dataset,
            }
        )

        update_status(**failed_status)

        save_json_atomic(
            SCAN_STATUS_PATH,
            failed_status,
        )

    finally:
        scan_lock.release()


# ============================================================
# UI PREPARATION
# ============================================================

def company_logo_url(company_name: str) -> str | None:
    company_name = company_name.strip()

    if not company_name or not LOGO_DEV_PUBLISHABLE_KEY:
        return None

    encoded_name = quote(company_name, safe="")
    encoded_key = quote(
        LOGO_DEV_PUBLISHABLE_KEY,
        safe="",
    )

    return (
        f"https://img.logo.dev/name/{encoded_name}"
        f"?token={encoded_key}"
        "&size=48&retina=true&format=webp"
    )


def fetch_brandfetch_logo(company_name: str) -> dict:
    if not BRANDFETCH_SECRET_API_KEY:
        return {}

    encoded_name = quote(company_name, safe="")
    response = get_thread_session().get(
        f"https://api.brandfetch.io/v2/search/{encoded_name}",
        headers={
            "Authorization": (
                f"Bearer {BRANDFETCH_SECRET_API_KEY}"
            ),
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    results = response.json()

    if not isinstance(results, list):
        raise ValueError(
            "Brandfetch Search returned an invalid response."
        )

    for result in results:
        if not isinstance(result, dict):
            continue

        logo_url = str(result.get("icon") or "").strip()
        parsed_logo_url = urlparse(logo_url)

        if (
            parsed_logo_url.scheme != "https"
            or parsed_logo_url.hostname
            not in {
                "asset.brandfetch.io",
                "cdn.brandfetch.io",
            }
            or BRANDFETCH_SECRET_API_KEY in logo_url
        ):
            continue

        return {
            "logo_url": logo_url,
            "domain": str(result.get("domain") or ""),
            "resolved_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    return {
        "logo_url": None,
        "domain": "",
        "resolved_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }


def normalize_company_names(
    company_names: list[str],
) -> dict[str, str]:
    return {
        re.sub(r"\s+", " ", name).strip().casefold(): name.strip()
        for name in company_names
        if name.strip()
    }


def load_brandfetch_logo_cache() -> dict:
    with brandfetch_logo_cache_lock:
        cached = load_json(
            BRANDFETCH_LOGO_CACHE_PATH,
            {},
        )

    return cached if isinstance(cached, dict) else {}


def brandfetch_logo_urls(
    normalized_names: dict[str, str],
    cached: dict,
) -> dict[str, str]:
    return {
        normalized_names[cache_key]: str(
            cached_entry.get("logo_url") or ""
        )
        for cache_key in normalized_names
        if isinstance(
            cached_entry := cached.get(cache_key),
            dict,
        )
        and cached_entry.get("logo_url")
    }


def cached_brandfetch_logos(
    company_names: list[str],
) -> tuple[dict[str, str], list[str]]:
    normalized_names = normalize_company_names(
        company_names
    )

    if not normalized_names:
        return {}, []

    cached = load_brandfetch_logo_cache()
    missing_names = [
        company_name
        for cache_key, company_name in normalized_names.items()
        if cache_key not in cached
    ]

    return (
        brandfetch_logo_urls(
            normalized_names,
            cached,
        ),
        missing_names,
    )


def resolve_brandfetch_logos(
    company_names: list[str],
) -> dict[str, str]:
    normalized_names = normalize_company_names(
        company_names
    )

    if not normalized_names:
        return {}

    cached = load_brandfetch_logo_cache()

    missing = {
        key: name
        for key, name in normalized_names.items()
        if key not in cached
    }

    updates: dict[str, dict] = {}

    if BRANDFETCH_SECRET_API_KEY and missing:
        worker_count = min(8, len(missing))

        with ThreadPoolExecutor(
            max_workers=worker_count
        ) as executor:
            futures = {
                executor.submit(
                    fetch_brandfetch_logo,
                    company_name,
                ): cache_key
                for cache_key, company_name in missing.items()
            }

            for future in as_completed(futures):
                cache_key = futures[future]

                try:
                    updates[cache_key] = future.result()
                except (
                    requests.RequestException,
                    ValueError,
                ) as error:
                    print(
                        "[warn] Could not resolve Brandfetch logo "
                        f"for {missing[cache_key]}: {error}"
                    )

    if updates:
        with brandfetch_logo_cache_lock:
            latest_cache = load_json(
                BRANDFETCH_LOGO_CACHE_PATH,
                {},
            )

            if not isinstance(latest_cache, dict):
                latest_cache = {}

            latest_cache.update(updates)
            save_json_atomic(
                BRANDFETCH_LOGO_CACHE_PATH,
                latest_cache,
            )
            cached = latest_cache

    return brandfetch_logo_urls(
        normalized_names,
        cached,
    )


def resolve_brandfetch_logos_in_background(
    company_names: list[str],
) -> None:
    try:
        resolve_brandfetch_logos(company_names)
    except Exception as error:
        print(
            "[warn] Background Brandfetch refresh failed: "
            f"{error}"
        )
    finally:
        brandfetch_logo_resolution_lock.release()


def schedule_brandfetch_logo_resolution(
    company_names: list[str],
) -> None:
    if (
        not BRANDFETCH_SECRET_API_KEY
        or not company_names
        or not brandfetch_logo_resolution_lock.acquire(
            blocking=False
        )
    ):
        return

    thread = threading.Thread(
        target=resolve_brandfetch_logos_in_background,
        args=(company_names,),
        daemon=True,
        name="brandfetch-logo-refresh",
    )

    try:
        thread.start()
    except RuntimeError as error:
        brandfetch_logo_resolution_lock.release()
        print(
            "[warn] Could not start Brandfetch refresh: "
            f"{error}"
        )


def prepare_jobs_for_ui(
    jobs: list[dict],
) -> list[dict]:
    prepared: list[dict] = []
    viewed_jobs = snapshot_viewed_jobs()
    company_names = [
        str(job.get("company") or "")
        for job in jobs
    ]
    (
        brandfetch_logos,
        missing_brandfetch_logos,
    ) = cached_brandfetch_logos(
        company_names
    )
    schedule_brandfetch_logo_resolution(
        missing_brandfetch_logos
    )

    for original_job in jobs:
        job = dict(original_job)

        analysis = job.get("analysis")

        if not isinstance(analysis, dict):
            analysis = fallback_analysis()

        job["analysis"] = analysis
        job["categories"] = title_categories(
            str(job.get("title") or "")
        )
        job["viewed_at"] = viewed_jobs.get(
            canonical_job_uid(str(job.get("uid") or ""))
        )
        company_name = str(job.get("company") or "")
        fallback_logo_url = company_logo_url(company_name)
        brandfetch_logo_url = brandfetch_logos.get(
            company_name
        )
        job["logo_url"] = (
            brandfetch_logo_url or fallback_logo_url
        )
        job["logo_fallback_url"] = (
            fallback_logo_url
            if brandfetch_logo_url
            else None
        )

        job["published_display"] = (
            display_timestamp(
                job.get("first_published_at")
            )
        )

        job["updated_display"] = (
            display_timestamp(
                job.get("source_updated_at")
            )
        )

        job["source_label"] = str(
            job.get("source") or ""
        ).title()

        job["team_display"] = (
            str(job.get("team") or "").strip()
            or str(
                analysis.get("team") or ""
            ).strip()
            or "Not listed."
        )

        prepared.append(job)

    return prepared


# ============================================================
# ROUTES
# ============================================================

@app.get("/")
def index():
    status = snapshot_status()

    selected_lookback = status.get(
        "lookback_hours",
        DEFAULT_LOOKBACK_HOURS,
    )

    if selected_lookback not in ALLOWED_LOOKBACK_HOURS:
        selected_lookback = DEFAULT_LOOKBACK_HOURS

    selected_dataset = str(
        status.get("dataset")
        or DEFAULT_COMPANY_DATASET
    )

    if selected_dataset not in COMPANY_DATASETS:
        selected_dataset = DEFAULT_COMPANY_DATASET

    jobs = load_visible_jobs(
        selected_lookback,
        selected_dataset,
    )

    prepared_jobs = prepare_jobs_for_ui(
        jobs
    )

    stats = {
        "total": len(prepared_jobs),
        **{
            ats: sum(
                1
                for job in prepared_jobs
                if job.get("source") == ats
            )
            for ats in SUPPORTED_ATS
        },
        "companies": len(
            {
                job.get("company")
                for job in prepared_jobs
                if job.get("company")
            }
        ),
    }

    return render_template(
        "index.html",
        jobs=prepared_jobs,
        stats=stats,
        status=status,
        last_scan_display=display_timestamp(
            status.get("last_scan_at")
        ),
        selected_lookback=selected_lookback,
        selected_dataset=selected_dataset,
        allowed_lookbacks=ALLOWED_LOOKBACK_HOURS,
        role_categories=ROLE_CATEGORY_LABELS,
        timezone_name=DISPLAY_TIMEZONE,
        ollama_enabled=USE_OLLAMA_ANALYSIS,
        ollama_model=OLLAMA_MODEL,
    )


@app.post("/api/scan")
def start_scan():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        payload = {}

    status = snapshot_status()

    try:
        lookback_hours = int(
            payload.get(
                "lookback_hours",
                DEFAULT_LOOKBACK_HOURS,
            )
        )
    except (TypeError, ValueError):
        return jsonify(
            {
                "ok": False,
                "message": (
                    "Invalid lookback time."
                ),
            }
        ), 400

    if lookback_hours not in ALLOWED_LOOKBACK_HOURS:
        return jsonify(
            {
                "ok": False,
                "message": (
                    "Lookback must be 1, 2, 4, 6, 12, "
                    "24, 48, or 72 hours."
                ),
            }
        ), 400

    dataset = str(
        payload.get("dataset")
        or status.get("dataset")
        or DEFAULT_COMPANY_DATASET
    )

    if dataset not in COMPANY_DATASETS:
        return jsonify(
            {
                "ok": False,
                "message": "Invalid company dataset.",
            }
        ), 400

    acquired = scan_lock.acquire(
        blocking=False
    )

    if not acquired:
        return jsonify(
            {
                "ok": False,
                "message": (
                    "A scan is already running."
                ),
            }
        ), 409

    thread = threading.Thread(
        target=scan_worker,
        args=(lookback_hours, dataset),
        daemon=True,
    )

    thread.start()

    return jsonify(
        {
            "ok": True,
            "message": (
                f"{lookback_hours}-hour scan started for "
                f"{COMPANY_DATASETS[dataset]['label']}."
            ),
        }
    ), 202


@app.get("/api/status")
def scan_status_api():
    return jsonify(snapshot_status())


@app.get("/api/health")
def health_api():
    catalogs = company_dataset_catalogs()
    status = snapshot_status()
    selected_dataset = str(
        status.get("dataset")
        or DEFAULT_COMPANY_DATASET
    )

    if selected_dataset not in COMPANY_DATASETS:
        selected_dataset = DEFAULT_COMPANY_DATASET

    selected_catalog = next(
        catalog
        for catalog in catalogs
        if catalog["id"] == selected_dataset
    )

    return jsonify(
        {
            "ok": True,
            "service": "atsift-scanner",
            "companies": selected_catalog["companies"],
            "companies_by_ats": selected_catalog[
                "companies_by_ats"
            ],
            "datasets": catalogs,
            "supported_ats": list(SUPPORTED_ATS),
            "ollama_enabled": USE_OLLAMA_ANALYSIS,
            "ollama_model": OLLAMA_MODEL,
        }
    )


@app.get("/api/jobs")
def jobs_api():
    status = snapshot_status()

    requested_lookback = request.args.get("lookback_hours")

    try:
        lookback_hours = int(
            requested_lookback
            if requested_lookback is not None
            else status.get(
                "lookback_hours",
                DEFAULT_LOOKBACK_HOURS,
            )
        )
    except (TypeError, ValueError):
        return jsonify(
            {
                "ok": False,
                "message": "Invalid lookback time.",
            }
        ), 400

    if lookback_hours not in ALLOWED_LOOKBACK_HOURS:
        return jsonify(
            {
                "ok": False,
                "message": (
                    "Lookback must be 1, 2, 4, 6, 12, "
                    "24, 48, or 72 hours."
                ),
            }
        ), 400

    dataset = str(
        request.args.get("dataset")
        or status.get("dataset")
        or DEFAULT_COMPANY_DATASET
    )

    if dataset not in COMPANY_DATASETS:
        return jsonify(
            {
                "ok": False,
                "message": "Invalid company dataset.",
            }
        ), 400

    return jsonify(
        prepare_jobs_for_ui(
            load_visible_jobs(
                lookback_hours,
                dataset,
            )
        )
    )


@app.post("/api/jobs/viewed")
def mark_job_viewed_api():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            {
                "ok": False,
                "message": "A job UID is required.",
            }
        ), 400

    uid = str(payload.get("uid") or "").strip()
    source = uid.split(":", 1)[0]

    if (
        not uid
        or len(uid) > 512
        or source not in SUPPORTED_ATS
        or ":" not in uid
    ):
        return jsonify(
            {
                "ok": False,
                "message": "Invalid job UID.",
            }
        ), 400

    viewed_at = mark_job_viewed(uid)

    return jsonify(
        {
            "ok": True,
            "uid": uid,
            "viewed_at": viewed_at,
        }
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    if AUTO_OPEN_BROWSER:
        Timer(
            1.0,
            lambda: webbrowser.open(
                f"http://{HOST}:{PORT}"
            ),
        ).start()

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        threaded=True,
    )
