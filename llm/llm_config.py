"""
Ollama settings and the response schema the analysis prompt is bound to.

Extracted from the previous scanner/config.py so the LLM layer stands on its
own. Bump ANALYSIS_PROMPT_VERSION whenever the prompt or the schema changes —
it is part of the cache fingerprint, so changing it retires stale analyses.
"""

from __future__ import annotations

USE_OLLAMA_ANALYSIS = True

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.2:3b"

MAX_DESCRIPTION_CHARS = 8_000

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
