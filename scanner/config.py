"""Settings, tunables and paths for the scanner."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)

DATA_DIR = BASE_DIR / "data"

# --- Company catalogs -------------------------------------------------------
#
# A company lands in a catalog by which adapter can read its board: the five
# token-slug boards share one, Workday gets its own because its slug is a full
# tenant URL, and anything else — a board no adapter covers, one that turned
# out not to answer, or a hand-picked extra not already in "main" — goes in
# "plus". Most of "plus" won't produce results by design; it's a holding pen
# for boards that can't be read, slugs that need a human look, and the small
# set of extras verified live but not yet folded into "main".

COMPANY_DATASETS = {
    "main": {
        "filename": "companies.csv",
        "label": "Greenhouse · Ashby · Lever · SmartRecruiters · Workable",
    },
    "workday": {
        "filename": "companies_workday.csv",
        "label": "Workday",
    },
    "plus": {
        "filename": "companies_plus.csv",
        "label": "Plus",
    },
}

DEFAULT_DATASET = "main"

COMPANY_DATASET_PATHS = {
    dataset_id: DATA_DIR / str(config["filename"])
    for dataset_id, config in COMPANY_DATASETS.items()
}

# --- Stores -----------------------------------------------------------------

JOBS_STORE_PATH = DATA_DIR / "jobs_store.json"
VIEWED_JOBS_PATH = DATA_DIR / "viewed_jobs.json"
ANALYSIS_CACHE_PATH = DATA_DIR / "analysis_cache.json"
SCAN_STATUS_PATH = DATA_DIR / "scan_status.json"
BRANDFETCH_LOGO_CACHE_PATH = DATA_DIR / "brandfetch_logo_cache.json"

# --- Timeframe --------------------------------------------------------------
#
# The window the user picks drives the scan AND the results. These are the
# options the UI offers; MAX_LOOKBACK_HOURS is the hard ceiling because
# freshness is the whole point of the product.
#
# The 1/2/4-hour windows exist for the "first 10 applicants" case: a sweep run
# on a schedule wants to see only what landed since the last one, and a 6-hour
# floor re-screens hours of postings that were already read.

LOOKBACK_OPTIONS = [1, 2, 4, 6, 12, 24, 48, 72]
DEFAULT_LOOKBACK_HOURS = 24
MAX_LOOKBACK_HOURS = 72

# --- Concurrency and HTTP ---------------------------------------------------

MAX_WORKERS = int(os.getenv("SCAN_MAX_WORKERS", "24"))
REQUEST_TIMEOUT = 15
RETRY_TOTAL = 2
RETRY_BACKOFF = 0.4
USER_AGENT = "ATSift/2.0 (+job board scanner)"

# --- LLM --------------------------------------------------------------------

USE_OLLAMA_ANALYSIS = os.getenv("USE_OLLAMA_ANALYSIS", "1") != "0"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
MAX_DESCRIPTION_CHARS = 8_000
ANALYSIS_PROMPT_VERSION = "job-analysis-v6-required-experience"

# By default every matched posting gets the same complete LLM analysis as the
# reference ATSift scanner. Set a positive value only when intentionally
# running a bounded development scan; zero means no cap.
MAX_ANALYSIS_PER_SCAN = int(os.getenv("MAX_ANALYSIS_PER_SCAN", "0"))

# The response format the analysis prompt is bound to. Ollama enforces this
# server-side, so the model cannot return a shape the parser does not expect.
JOB_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "us_location_eligible": {"type": "string", "enum": ["YES", "NO"]},
        "opt_eligible": {"type": "string", "enum": ["YES", "NO"]},
        "opt_blocking_line": {"type": "string"},
        "degree": {"type": "string"},
        "qualifications": {"type": "string"},
        "eligibility": {"type": "string"},
        "key_tech_skills": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 15,
        },
        "experience_years": {"type": "string"},
        "minimum_years": {"type": ["number", "null"]},
        "ats_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "tip": {"type": "string"},
        "salary": {"type": "string"},
        "team": {"type": "string"},
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

# --- Server -----------------------------------------------------------------

# Not Flask's usual 5000: macOS AirPlay Receiver binds that port and answers
# 403, which the dashboard's health probe cannot tell apart from a scanner
# that is simply down.
PORT = int(os.getenv("SCANNER_PORT", "5057"))
SCANNER_API_TOKEN = os.getenv("SCANNER_API_TOKEN", "").strip()

LOGO_DEV_PUBLISHABLE_KEY = os.getenv("LOGO_DEV_PUBLISHABLE_KEY", "").strip()
LOGO_DEV_SECRET_KEY = os.getenv("LOGO_DEV_SECRET_KEY", "").strip()
BRANDFETCH_CLIENT_ID = os.getenv("BRANDFETCH_CLIENT_ID", "").strip()
BRANDFETCH_SECRET_API_KEY = os.getenv("BRANDFETCH_SECRET_API_KEY", "").strip()
