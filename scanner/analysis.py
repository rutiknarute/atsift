"""
Screening a posting with a local Ollama model.

Analysis is cached by a fingerprint of the fields the model actually reads, so
re-scanning an unchanged posting never pays for a second inference.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

import requests

from scanner.config import (
    ANALYSIS_PROMPT_VERSION,
    JOB_ANALYSIS_SCHEMA,
    MAX_DESCRIPTION_CHARS,
    OLLAMA_MODEL,
    OLLAMA_URL,
    USE_OLLAMA_ANALYSIS,
)
from scanner.experience import resolve_experience
from scanner.text import compact_list, compact_text, strip_html

_SKILL_TERMS = (
    ("Python", r"\bpython\b"),
    ("Java", r"\bjava\b"),
    ("JavaScript", r"\bjavascript\b"),
    ("TypeScript", r"\btypescript\b"),
    ("React", r"\breact(?:\.js)?\b"),
    ("Next.js", r"\bnext\.?js\b"),
    ("Node.js", r"\bnode\.?js\b"),
    ("Go", r"\bgolang\b|\bgo programming\b"),
    ("C++", r"(?<!\w)c\+\+(?!\w)"),
    ("C#", r"(?<!\w)c#(?!\w)"),
    ("SQL", r"\bsql\b"),
    ("PostgreSQL", r"\bpostgres(?:ql)?\b"),
    ("MySQL", r"\bmysql\b"),
    ("MongoDB", r"\bmongodb\b"),
    ("Redis", r"\bredis\b"),
    ("AWS", r"\baws\b|amazon web services"),
    ("Azure", r"\bazure\b"),
    ("Google Cloud", r"\bgcp\b|google cloud"),
    ("Docker", r"\bdocker\b"),
    ("Kubernetes", r"\bkubernetes\b|\bk8s\b"),
    ("Terraform", r"\bterraform\b"),
    ("Linux", r"\blinux\b"),
    ("Git", r"\bgit\b"),
    ("REST APIs", r"\brest(?:ful)?\s+apis?\b"),
    ("GraphQL", r"\bgraphql\b"),
    ("Kafka", r"\bkafka\b"),
    ("Spark", r"\bapache spark\b|\bspark\b"),
    ("Snowflake", r"\bsnowflake\b"),
    ("Databricks", r"\bdatabricks\b"),
    ("Tableau", r"\btableau\b"),
    ("Power BI", r"\bpower\s*bi\b"),
    ("Excel", r"\bexcel\b"),
    ("Salesforce", r"\bsalesforce\b"),
    ("Machine Learning", r"\bmachine learning\b"),
    ("Deep Learning", r"\bdeep learning\b"),
    ("LLMs", r"\bllms?\b|large language models?"),
    ("Generative AI", r"\bgenerative ai\b|\bgenai\b"),
    ("NLP", r"\bnlp\b|natural language processing"),
    ("Computer Vision", r"\bcomputer vision\b"),
    ("Data Analysis", r"\bdata analysis\b|\bdata analytics\b"),
    ("Data Engineering", r"\bdata engineering\b"),
    ("ETL", r"\betl\b|\belt\b"),
    ("CI/CD", r"\bci/?cd\b|continuous integration"),
    ("Agile", r"\bagile\b"),
    ("Product Management", r"\bproduct management\b"),
)


def _description_sentences(value: str | None) -> list[str]:
    text = strip_html(str(value or ""))

    return [
        compact_text(part, default="", maximum=260)
        for part in re.split(r"\n+|(?<=[.!?;])\s+", text)
        if part.strip()
    ]


def _first_sentence(sentences: list[str], pattern: str) -> str:
    matcher = re.compile(pattern, re.IGNORECASE)

    return next(
        (sentence for sentence in sentences if matcher.search(sentence)),
        "",
    )


def _deterministic_skills(description: str) -> list[str]:
    return [
        label
        for label, pattern in _SKILL_TERMS
        if re.search(pattern, description, re.IGNORECASE)
    ][:15]


def _deterministic_salary(
    salary_context: str,
    sentences: list[str],
) -> str:
    if salary_context.strip():
        return compact_text(salary_context, maximum=180)

    salary = _first_sentence(
        sentences,
        r"(?:\$|usd\b|salary|compensation).{0,120}"
        r"(?:\d[\d,.]*\s*(?:k|per year|annually)?)",
    )

    return salary or "Not listed."


def analysis_description(value: str | None) -> str:
    """
    Keep requirements visible even when a long JD exceeds the model budget.

    ATS descriptions often put employer boilerplate first and qualifications
    near the end. A plain prefix truncation is therefore biased against the
    exact experience evidence this analysis needs.
    """

    description = strip_html(str(value or "")).strip()

    if len(description) <= MAX_DESCRIPTION_CHARS:
        return description

    excerpts = [
        part.strip()
        for part in re.split(r"\n+|(?<=[.!?;])\s+", description)
        if re.search(
            r"\b(?:experience|years?|months?|qualifications?|requirements?)\b",
            part,
            re.IGNORECASE,
        )
    ]
    evidence = "\n".join(excerpts)
    evidence_budget = min(2_500, MAX_DESCRIPTION_CHARS // 3)
    evidence = evidence[:evidence_budget]
    remaining = MAX_DESCRIPTION_CHARS - len(evidence) - 48
    head_size = max(0, int(remaining * 0.65))
    tail_size = max(0, remaining - head_size)

    return (
        f"{description[:head_size]}\n\n"
        "REQUIREMENT EXCERPTS\n"
        f"{evidence}\n\n"
        f"{description[-tail_size:] if tail_size else ''}"
    )[:MAX_DESCRIPTION_CHARS]


def analysis_fingerprint(job: dict) -> str:
    source_text = "|".join(
        [
            ANALYSIS_PROMPT_VERSION,
            OLLAMA_MODEL,
            str(job.get("title") or ""),
            str(job.get("location") or ""),
            str(job.get("team") or ""),
            str(job.get("salary_context") or ""),
            str(job.get("description") or ""),
        ]
    )

    return hashlib.sha256(
        source_text.encode("utf-8")
    ).hexdigest()


def fallback_analysis(job: dict | None = None) -> dict:
    source_job = job or {}
    description = strip_html(
        str(source_job.get("description") or "")
    )
    sentences = _description_sentences(description)
    experience = resolve_experience(
        experience_text=None,
        model_minimum=None,
        description=description,
    )
    degree = _first_sentence(
        sentences,
        r"\b("
        r"bachelor'?s?|master'?s?|ph\.?d|doctorate|"
        r"associate'?s?|college degree|university degree|degree in"
        r")\b",
    )
    blocker = _first_sentence(
        sentences,
        r"\b("
        r"no (?:current or future )?sponsorship|"
        r"without (?:the need for )?sponsorship|"
        r"unable to sponsor|not (?:eligible|available) for sponsorship|"
        r"u\.?s\.? citizens? only|required u\.?s\.? citizenship|"
        r"permanent residents? only|security clearance"
        r")\b",
    )
    skills = _deterministic_skills(description)
    qualifications = (
        experience.text
        if experience.minimum_years is not None
        else (
            _first_sentence(
                sentences,
                r"\b(required qualifications?|minimum qualifications?|"
                r"what you(?:'|’)ll bring|what you bring|you have|must have)\b",
            )
            or "Review the qualifications in the full posting."
        )
    )
    stop_after_experience = (
        experience.minimum_years is not None
        and experience.minimum_years >= 4
    )

    return {
        "us_location_eligible": "UNKNOWN",
        "opt_eligible": "NO" if blocker else "UNKNOWN",
        "opt_blocking_line": blocker,
        "degree": degree or "Not stated in JD.",
        "qualifications": qualifications,
        "eligibility": (
            blocker
            or "No explicit work-authorization restriction was found "
            "by the rule-based review."
        ),
        "key_tech_skills": skills,
        "experience_years": experience.text,
        "minimum_years": experience.minimum_years,
        "experience_fit": (
            "NO"
            if stop_after_experience
            else (
                "YES"
                if experience.minimum_years is not None
                else "UNKNOWN"
            )
        ),
        "stop_after_experience": stop_after_experience,
        "ats_keywords": skills,
        "tip": (
            "Verify the extracted requirements against the full posting "
            "before applying."
        ),
        "salary": _deterministic_salary(
            str(source_job.get("salary_context") or ""),
            sentences,
        ),
        "team": compact_text(
            source_job.get("team"),
            default="Not listed.",
            maximum=160,
        ),
        "analysis_failed": True,
    }


def normalize_analysis(result: dict, job: dict | None = None) -> dict:
    source_job = job or {}
    experience = resolve_experience(
        experience_text=result.get("experience_years"),
        model_minimum=result.get("minimum_years"),
        qualifications=result.get("qualifications"),
        degree=result.get("degree"),
        description=source_job.get("description"),
    )
    minimum_years = experience.minimum_years

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
        "experience_years": experience.text,
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
    description = analysis_description(job.get("description"))

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
- Extract every mandatory professional-experience clause.
- Ignore preferred experience unless it is also required.
- minimum_years must be a number or null.
- experience_years must quote or closely preserve the JD's concise
  mandatory experience requirement, including every required number and unit.
- When requirements are joined by AND or WITH, minimum_years is the highest
  lower bound because the candidate must satisfy all of them.
- When genuinely alternative paths are joined by OR, minimum_years is the
  lowest lower bound because either path satisfies the posting.
- Do not count years attached only to education, age, a certification,
  product history, or a preferred/nice-to-have qualification.
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

        return normalize_analysis(parsed, job)

    except (
        requests.RequestException,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"[warn] Ollama analysis failed for "
            f"'{job.get('title')}': {error}"
        )

        return fallback_analysis(job)


def get_job_analysis(
    job: dict,
    cache: dict,
) -> dict:
    if not USE_OLLAMA_ANALYSIS:
        return fallback_analysis(job)

    uid = job["uid"]
    fingerprint = analysis_fingerprint(job)

    cached = cache.get(uid)

    if (
        isinstance(cached, dict)
        and cached.get("fingerprint") == fingerprint
        and isinstance(cached.get("analysis"), dict)
    ):
        normalized = normalize_analysis(cached["analysis"], job)

        if normalized != cached["analysis"]:
            cached["analysis"] = normalized

        return normalized

    analysis = analyze_job_with_ollama(job)

    cache[uid] = {
        "fingerprint": fingerprint,
        "analysis": analysis,
        "analyzed_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    return analysis


def normalize_job_analysis(job: dict) -> dict:
    """Repair a stored analysis against its retained JD text."""

    analysis = job.get("analysis")

    if not isinstance(analysis, dict):
        job["analysis"] = fallback_analysis(job)

        return job

    if analysis.get("analysis_failed"):
        job["analysis"] = fallback_analysis(job)

        return job

    job["analysis"] = normalize_analysis(analysis, job)

    return job
