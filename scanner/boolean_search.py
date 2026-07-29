"""
The boolean search: include keywords AND NOT exclude keywords, per category.

This is the filter that defines the product. Patterns are compiled once at
import and reused — titles get checked tens of thousands of times per scan.

See docs/boolean-search.md for the full rationale.
"""

from __future__ import annotations

import re

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

    Longest keywords first, so the longest alternative wins before a shorter
    prefix can claim the match.

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
        compile_keyword_pattern(ROLE_CATEGORY_EXCLUDES[category]),
    )
    for category, keywords in ROLE_CATEGORY_KEYWORDS.items()
}

ALL_CATEGORIES = list(ROLE_CATEGORY_KEYWORDS)


def title_categories(
    title: str | None,
    categories: list[str] | None = None,
) -> list[str]:
    """
    Return every requested role category matched by a job title.

    A title can land in several categories at once; that overlap is intentional
    and the caller gets all of them.
    """

    if not title:
        return []

    wanted = categories or ALL_CATEGORIES

    return [
        category
        for category in wanted
        if category in ROLE_CATEGORY_PATTERNS
        and ROLE_CATEGORY_PATTERNS[category][0].search(title)
        and not ROLE_CATEGORY_PATTERNS[category][1].search(title)
    ]


def title_matches_keywords(
    title: str | None,
    categories: list[str] | None = None,
) -> bool:
    """Return True when at least one requested role category matches."""

    return bool(title_categories(title, categories))
