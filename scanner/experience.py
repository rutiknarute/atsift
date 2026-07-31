"""Deterministic validation for experience requirements extracted by the LLM.

The local model is useful for finding the relevant requirement, but small
models are inconsistent about copying that requirement into ``minimum_years``.
This module treats the JD text as the source of truth and repairs common model
outputs such as ``"Yes"``, ``"2-4 years"`` with a null numeric value, or a
numeric value that contradicts the extracted sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scanner.text import compact_text, strip_html

_NUMBER_WORDS = {
    "zero": 0.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
    "eleven": 11.0,
    "twelve": 12.0,
    "fifteen": 15.0,
    "twenty": 20.0,
}
_NUMBER_TOKEN = (
    r"(?:\d+(?:\.\d+)?|"
    + "|".join(_NUMBER_WORDS)
    + r")"
)
_RANGE = re.compile(
    rf"(?P<low>{_NUMBER_TOKEN})\s*"
    r"(?:\+?\s*[-–—]\s*|(?:to|through)\s+)"
    rf"(?P<high>{_NUMBER_TOKEN})\s*\+?\s*"
    r"(?P<unit>years?|yrs?|months?|mos?)\b",
    re.IGNORECASE,
)
_BETWEEN_RANGE = re.compile(
    rf"\bbetween\s+(?P<low>{_NUMBER_TOKEN})\s+and\s+"
    rf"(?P<high>{_NUMBER_TOKEN})\s+"
    r"(?P<unit>years?|yrs?|months?|mos?)\b",
    re.IGNORECASE,
)
_SINGLE = re.compile(
    rf"(?:>=?\s*|(?:at\s+least|minimum(?:\s+of)?)\s+)?"
    rf"(?P<value>{_NUMBER_TOKEN})\s*\+?\s*"
    r"(?P<unit>years?|yrs?|months?|mos?)\b",
    re.IGNORECASE,
)
_COMPACT_NUMBER = re.compile(
    rf"^\s*(?:>=?\s*)?(?P<value>{_NUMBER_TOKEN})\s*\+?\s*$",
    re.IGNORECASE,
)
_COMPACT_RANGE = re.compile(
    rf"^\s*(?P<low>{_NUMBER_TOKEN})\s*[-–—]\s*"
    rf"(?P<high>{_NUMBER_TOKEN})\s*\+?\s*$",
    re.IGNORECASE,
)
_EXPERIENCE_CONTEXT = re.compile(
    r"\b("
    r"experience|experienced|background|track record|"
    r"professional work|industry work|hands-on work"
    r")\b",
    re.IGNORECASE,
)
_OPTIONAL_CONTEXT = re.compile(
    r"\b("
    r"preferred|ideally|nice[- ]to[- ]have|bonus|a plus|desired"
    r")\b",
    re.IGNORECASE,
)
_REQUIRED_CONTEXT = re.compile(
    r"\b(required|requirement|must|minimum|at least|you have|have \d)\b",
    re.IGNORECASE,
)
_JUNK = re.compile(
    r"^(?:"
    r"yes|no|n/?a|none|null|unknown|not (?:clearly )?"
    r"(?:specified|stated|listed)|analysis unavailable"
    r")\.?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExperienceRequirement:
    text: str
    minimum_years: float | None


def _number(value: str) -> float:
    lowered = value.strip().casefold()

    if lowered in _NUMBER_WORDS:
        return _NUMBER_WORDS[lowered]

    return float(lowered)


def _as_years(value: float, unit: str) -> float:
    if unit.casefold().startswith(("month", "mo")):
        return round(value / 12, 2)

    return value


def coerce_years(value) -> float | None:
    """Return a plausible numeric year count or ``None``."""

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        years = float(value)
    elif isinstance(value, str):
        match = _COMPACT_NUMBER.fullmatch(value)

        if not match:
            return None

        years = _number(match.group("value"))
    else:
        return None

    if years < 0 or years > 50:
        return None

    return int(years) if years.is_integer() else years


def _clauses(text: str) -> list[str]:
    normalized = re.sub(
        r"[\t\r ]+",
        " ",
        strip_html(str(text or "")),
    )
    normalized = re.sub(
        r"\n+\s*or\s*\n+",
        " OR ",
        normalized,
        flags=re.IGNORECASE,
    )

    return [
        clause.strip(" \n-*•;")
        for clause in re.split(r"\n+|(?<=[.!?;])\s+|[•●▪]", normalized)
        if clause.strip(" \n-*•;")
    ]


def _values_in_clause(clause: str, *, compact: bool) -> list[float]:
    values: list[float] = []
    occupied: list[tuple[int, int]] = []

    for pattern in (_BETWEEN_RANGE, _RANGE):
        for match in pattern.finditer(clause):
            values.append(
                _as_years(
                    _number(match.group("low")),
                    match.group("unit"),
                )
            )
            occupied.append(match.span())

    for match in _SINGLE.finditer(clause):
        if any(
            start <= match.start() < end
            for start, end in occupied
        ):
            continue

        values.append(
            _as_years(
                _number(match.group("value")),
                match.group("unit"),
            )
        )

    if not values and compact:
        range_match = _COMPACT_RANGE.fullmatch(clause)

        if range_match:
            values.append(_number(range_match.group("low")))
        else:
            match = _COMPACT_NUMBER.fullmatch(clause)

            if match:
                values.append(_number(match.group("value")))

    return values


def _has_numeric_or_alternatives(clause: str) -> bool:
    branches = re.split(r"\bor\b", clause, flags=re.IGNORECASE)

    if len(branches) < 2:
        return False

    branches_with_years = sum(
        bool(_values_in_clause(branch, compact=False))
        for branch in branches
    )

    return branches_with_years >= 2


def minimum_years_from_text(
    text: str | None,
    *,
    require_experience_context: bool = False,
) -> float | None:
    """
    Resolve the experience floor represented by text.

    Ranges use their lower bound. Multiple mandatory clauses use the highest
    floor because all requirements must be met. Explicit ``or`` alternatives
    use the lowest floor because either path satisfies the posting.
    """

    resolved: list[float] = []

    for clause in _clauses(str(text or "")):
        if (
            require_experience_context
            and not _EXPERIENCE_CONTEXT.search(clause)
        ):
            continue

        if (
            _OPTIONAL_CONTEXT.search(clause)
            and not _REQUIRED_CONTEXT.search(clause)
        ):
            continue

        values = _values_in_clause(
            clause,
            compact=not require_experience_context,
        )

        if not values:
            continue

        resolved.append(
            min(values)
            if _has_numeric_or_alternatives(clause)
            else max(values)
        )

    if not resolved:
        return None

    minimum = max(resolved)

    return int(minimum) if minimum.is_integer() else minimum


def _usable_summary(value: str | None) -> str:
    text = compact_text(
        strip_html(str(value or "")),
        default="",
        maximum=180,
    )

    if not text or _JUNK.fullmatch(text):
        return ""

    if minimum_years_from_text(text) is None:
        return ""

    compact_range = _COMPACT_RANGE.fullmatch(text)

    if compact_range:
        return (
            f"{compact_range.group('low')}–"
            f"{compact_range.group('high')} years"
        )

    compact_number = _COMPACT_NUMBER.fullmatch(text)

    if compact_number:
        number = compact_number.group("value")

        if text.lstrip().startswith(">"):
            return f"At least {number} years"

        suffix = "+" if "+" in text else ""

        return f"{number}{suffix} years"

    return text


def extract_required_experience(
    description: str | None,
) -> ExperienceRequirement:
    """Extract the strongest mandatory experience clause from a plain-text JD."""

    candidates: list[tuple[float, str]] = []

    for clause in _clauses(str(description or "")):
        if not _EXPERIENCE_CONTEXT.search(clause):
            continue

        if (
            _OPTIONAL_CONTEXT.search(clause)
            and not _REQUIRED_CONTEXT.search(clause)
        ):
            continue

        minimum = minimum_years_from_text(
            clause,
            require_experience_context=True,
        )

        if minimum is not None:
            candidates.append((minimum, clause))

    if not candidates:
        return ExperienceRequirement("", None)

    minimum = max(value for value, _ in candidates)
    matching = [text for value, text in candidates if value == minimum]
    summary = compact_text(
        matching[0],
        default="",
        maximum=180,
    )

    return ExperienceRequirement(summary, minimum)


def resolve_experience(
    *,
    experience_text: str | None,
    model_minimum,
    qualifications: str | None = None,
    degree: str | None = None,
    description: str | None = None,
) -> ExperienceRequirement:
    """Reconcile LLM fields with the source text, preferring quoted evidence."""

    summary = _usable_summary(experience_text)
    extracted = extract_required_experience(description)
    derived = extracted.minimum_years

    if derived is None:
        derived = minimum_years_from_text(summary)

    if derived is None:
        derived = minimum_years_from_text(qualifications)

    if derived is None:
        derived = minimum_years_from_text(degree)

    minimum = derived

    if minimum is None:
        minimum = coerce_years(model_minimum)

    summary_minimum = minimum_years_from_text(summary)

    if (
        extracted.text
        and (
            not summary
            or (
                extracted.minimum_years is not None
                and summary_minimum != extracted.minimum_years
            )
        )
    ):
        summary = extracted.text

    if not summary:
        qualification_summary = _usable_summary(qualifications)
        degree_summary = _usable_summary(degree)
        summary = (
            qualification_summary
            or degree_summary
        )

    if not summary and minimum is not None:
        summary = f"{minimum:g}+ years"

    return ExperienceRequirement(
        summary or "Not clearly stated.",
        minimum,
    )
