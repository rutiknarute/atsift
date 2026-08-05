"""Loading the verified company catalogs."""

from __future__ import annotations

import csv
from functools import lru_cache

from scanner.ats import SUPPORTED_ATS
from scanner.config import (
    COMPANY_DATASET_PATHS,
    COMPANY_DATASETS,
    DEFAULT_DATASET,
)


def resolve_dataset(dataset_id: str | None) -> str:
    key = str(dataset_id or "").strip().lower()

    return key if key in COMPANY_DATASETS else DEFAULT_DATASET


def dataset_for_ats(ats: str | None) -> str:
    """
    Which catalog a company belongs in, decided by its board.

    Workday is its own catalog because its slug is a full tenant URL. A board
    no adapter covers goes to "plus" — kept, but knowingly unscannable.

    This is the floor, not the whole rule: `scripts/import_companies.py
    --verify` also parks a row here when the board it names does not answer,
    so "plus" holds boards nothing can read, boards that turned out not to
    exist, and hand-verified extras not yet folded into "main".
    """

    key = str(ats or "").strip().lower()

    if key == "workday":
        return "workday"

    return DEFAULT_DATASET if key in SUPPORTED_ATS else "plus"


@lru_cache(maxsize=4)
def load_companies(dataset_id: str = DEFAULT_DATASET) -> tuple[dict, ...]:
    """
    Read a catalog as (name, ats, slug) rows.

    Cached — the file is static during a run and gets read on every scan.
    """

    dataset = resolve_dataset(dataset_id)
    path = COMPANY_DATASET_PATHS[dataset]

    if not path.exists():
        return ()

    companies: list[dict] = []
    seen: set[tuple[str, str]] = set()

    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = str(row.get("name") or "").strip()
            ats = str(row.get("ats") or "").strip().lower()
            slug = str(row.get("slug") or "").strip()

            if not name or not ats or not slug:
                continue

            key = (ats, slug)

            if key in seen:
                continue

            seen.add(key)
            companies.append({"name": name, "ats": ats, "slug": slug})

    return tuple(companies)


def dataset_summary() -> list[dict]:
    summary = []

    for dataset_id, config in COMPANY_DATASETS.items():
        summary.append(
            {
                "id": dataset_id,
                "label": config["label"],
                "count": len(load_companies(dataset_id)),
            }
        )

    return summary
