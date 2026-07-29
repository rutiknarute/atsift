"""
The two text helpers the LLM analysis layer depends on.

Extracted from the previous scanner/text.py. Model output is loosely typed —
these collapse it into short, displayable strings and deduplicated lists.
"""

from __future__ import annotations

import re


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
