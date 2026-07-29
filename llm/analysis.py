"""
Screening a posting with a local Ollama model.

Analysis is cached by a fingerprint of the fields the model actually reads, so
re-scanning an unchanged posting never pays for a second inference.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import requests

from llm_config import (
    ANALYSIS_PROMPT_VERSION,
    JOB_ANALYSIS_SCHEMA,
    MAX_DESCRIPTION_CHARS,
    OLLAMA_MODEL,
    OLLAMA_URL,
    USE_OLLAMA_ANALYSIS,
)
from text_helpers import compact_list, compact_text

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
