"""Turning the loosely-typed text an ATS returns into displayable strings."""

from __future__ import annotations

import html
import re


def strip_html(raw_html: str | None) -> str:
    """Flatten an HTML job description into readable plain text."""

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
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)

    return text.strip()


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


def compact_list(value, maximum_items: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()

    for item in value:
        text = compact_text(item, default="", maximum=80)
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

    names = [
        str(item.get("name") or "").strip()
        for item in value
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]

    return ", ".join(names)


def location_name(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()

    return str(value or "").strip()
