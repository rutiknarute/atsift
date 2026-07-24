"""
Greenhouse + Ashby job board scraper
Pulls postings first published in the last N hours, from public JSON APIs.
Filters titles with an include/exclude keyword list, then optionally with a
local Llama 3.2 model via Ollama for a final relevance check.

Two distinct date fields are tracked separately:
  - first_published_at : when the job was originally posted (the freshness signal)
  - source_updated_at  : when the ATS last touched the record (Greenhouse only;
                          not exposed by Ashby's public job-board API)
"""

import csv
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------- CONFIG ----------
LOOKBACK_HOURS = 48
COMPANY_LIST_FILE = "companies.csv"   # columns: name, ats, slug
OUTPUT_FILE = "new_jobs.csv"
SEEN_IDS_FILE = "seen_ids.json"        # persisted between runs to avoid re-emitting
REQUEST_DELAY_SEC = 0.5                # be polite, avoid hammering
TIMEOUT = 15

# ---------- KEYWORD FILTER ----------
# A job title must contain at least one INCLUDE term and NO EXCLUDE term.
INCLUDE_KEYWORDS = [
    "software", "ai software", "application developer", "sde", "full stack",
    "full-stack", "frontend", "front end", "backend", "back end",
    "web developer", "ui", "platform engineer", "swe", "product engineer",
    "associate developer", "application", "python", "university",
]
EXCLUDE_KEYWORDS = [
    "senior", "sr", "lead", "staff", "manager", "principal", "director",
    "vp", "vice president", "embedded", "phd", "head", "architect",
]


def _compile_keyword_pattern(keywords):
    # Word-boundary match so short terms like "ui" or "sde" don't match
    # inside unrelated words (e.g. "ui" inside "build").
    escaped = [re.escape(kw.lower()) for kw in keywords]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b")


_INCLUDE_PATTERN = _compile_keyword_pattern(INCLUDE_KEYWORDS)
_EXCLUDE_PATTERN = _compile_keyword_pattern(EXCLUDE_KEYWORDS)


def title_matches_keywords(title):
    """True if title contains an include keyword and no exclude keyword."""
    if not title:
        return False
    t = title.lower()
    if not _INCLUDE_PATTERN.search(t):
        return False
    if _EXCLUDE_PATTERN.search(t):
        return False
    return True


# ---------- OLLAMA (LOCAL LLM) FILTER ----------
# Optional second-pass relevance check, on top of the keyword filter above.
# Set to False to rely on the keyword filter alone.
USE_LLM_FILTER = True
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
RELEVANCE_CRITERIA = "software engineering roles, especially backend or full-stack positions"


def is_relevant(title, criteria=RELEVANCE_CRITERIA):
    """Ask local Llama 3.2 (via Ollama) whether a job title matches what we want."""
    prompt = (
        f"Job title: \"{title}\"\n"
        f"Criteria: {criteria}\n"
        "Does this job title match the criteria? Answer with exactly one word: yes or no."
    )
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip().lower()
        return answer.startswith("yes")
    except requests.RequestException as e:
        print(f"[warn] Ollama call failed for '{title}': {e}")
        return True  # fail open


# ---------- HELPERS ----------
def load_companies(path):
    companies = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            companies.append(row)
    return companies


def load_seen_ids(path):
    if Path(path).exists():
        try:
            with open(path, encoding="utf-8") as f:
                values = json.load(f)
        except (OSError, json.JSONDecodeError) as error:
            print(f"[warn] Could not read {path}: {error}")
            return set()

        if isinstance(values, list):
            return {str(value) for value in values}

    return set()


def save_seen_ids(path, ids):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f)


def is_recent(iso_date_str, hours):
    if not iso_date_str:
        return False
    try:
        dt = datetime.fromisoformat(iso_date_str.replace("Z", "+00:00"))
    except ValueError:
        return False

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt >= datetime.now(timezone.utc) - timedelta(hours=hours)


# ---------- FETCHERS ----------
def fetch_greenhouse(slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    resp = requests.get(url, timeout=TIMEOUT)
    if resp.status_code != 200:
        return []
    data = resp.json()
    results = []
    for job in data.get("jobs", []):
        results.append({
            "source": "greenhouse",
            "company": slug,
            "id": str(job.get("id")),
            "title": job.get("title"),
            "location": (job.get("location") or {}).get("name"),
            "first_published_at": job.get("first_published"),
            "source_updated_at": job.get("updated_at"),
            "url": job.get("absolute_url"),
        })
    return results


def fetch_ashby(slug):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    resp = requests.get(url, timeout=TIMEOUT)
    if resp.status_code != 200:
        return []
    data = resp.json()
    results = []
    for job in data.get("jobs", []):
        results.append({
            "source": "ashby",
            "company": slug,
            "id": str(job.get("id")),
            "title": job.get("title"),
            "location": job.get("location"),
            "first_published_at": job.get("publishedAt"),
            "source_updated_at": None,  # not exposed by Ashby's public job-board API
            "url": job.get("jobUrl") or job.get("applyUrl"),
        })
    return results


# ---------- MAIN ----------
def main():
    companies = load_companies(COMPANY_LIST_FILE)
    seen_ids = load_seen_ids(SEEN_IDS_FILE)

    new_rows = []
    for company in companies:
        slug = company["slug"]
        ats = company["ats"].strip().lower()

        try:
            if ats == "greenhouse":
                jobs = fetch_greenhouse(slug)
            elif ats == "ashby":
                jobs = fetch_ashby(slug)
            else:
                continue
        except requests.RequestException as e:
            print(f"[warn] failed to fetch {slug} ({ats}): {e}")
            continue

        for job in jobs:
            uid = (
                f"{job['source'].casefold()}:"
                f"{job['company'].casefold()}:"
                f"{job['id']}"
            )
            if uid in seen_ids:
                continue

            # 1) freshness
            if not is_recent(job.get("first_published_at"), LOOKBACK_HOURS):
                continue

            # 2) keyword include/exclude filter (fast, no LLM call)
            if not title_matches_keywords(job["title"]):
                seen_ids.add(uid)
                continue

            # 3) optional local-LLM relevance check on top
            if USE_LLM_FILTER and not is_relevant(job["title"]):
                seen_ids.add(uid)
                continue

            new_rows.append(job)
            seen_ids.add(uid)

        time.sleep(REQUEST_DELAY_SEC)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "source", "company", "id", "title", "location",
            "first_published_at", "source_updated_at", "url",
        ])
        writer.writeheader()
        writer.writerows(new_rows)

    if new_rows:
        print(f"Wrote {len(new_rows)} new jobs to {OUTPUT_FILE}")
    else:
        print("No new jobs found in this run.")

    save_seen_ids(SEEN_IDS_FILE, seen_ids)


if __name__ == "__main__":
    main()
