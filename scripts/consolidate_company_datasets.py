"""Build the three authoritative scan catalogs from the legacy partitions.

The original six reusable platforms (Ashby, Greenhouse, Lever, Rippling,
SmartRecruiters, Workable) are consolidated in `companies_core_ats.csv`.
Larger enterprise multi-tenant platforms (Workday, iCIMS, Oracle, Avature,
SuccessFactors, Jibe) go in `companies_enterprise_ats.csv`. Dedicated
company-specific adapters are kept in `companies_direct.csv`. Source
partitions remain as provenance and as inputs for repeatable rebuilds, but
are no longer selectable scan datasets.

    python3 scripts/consolidate_company_datasets.py
    python3 scripts/consolidate_company_datasets.py --check
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scanner.ats import SUPPORTED_ATS  # noqa: E402
from scanner.companies import DIRECT_ATS, ENTERPRISE_ATS  # noqa: E402

DATA_DIR = BASE_DIR / "data"
SOURCE_PATHS = (
    DATA_DIR / "companies.csv",
    DATA_DIR / "companies_rippling.csv",
    DATA_DIR / "companies_workday.csv",
    DATA_DIR / "companies_icims.csv",
)
OUTPUT_PATHS = {
    "core": DATA_DIR / "companies_core_ats.csv",
    "enterprise": DATA_DIR / "companies_enterprise_ats.csv",
    "direct": DATA_DIR / "companies_direct.csv",
}
FIELDS = ["name", "ats", "slug", "source_url"]


def read_sources() -> list[dict]:
    rows = []

    for path in SOURCE_PATHS:
        with open(path, newline="", encoding="utf-8") as handle:
            for raw in csv.DictReader(handle):
                row = {
                    field: str(raw.get(field) or "").strip()
                    for field in FIELDS
                }

                if row["name"] and row["ats"] and row["slug"]:
                    row["ats"] = row["ats"].lower()
                    rows.append(row)

    return rows


def consolidate(rows: list[dict]) -> dict[str, list[dict]]:
    catalogs: dict[str, dict[tuple[str, str], dict]] = {
        "core": {},
        "enterprise": {},
        "direct": {},
    }

    for row in rows:
        ats = row["ats"]

        if ats not in SUPPORTED_ATS:
            raise ValueError(f"unsupported ATS in source catalogs: {ats}")

        if ats in DIRECT_ATS:
            dataset = "direct"
        elif ats in ENTERPRISE_ATS:
            dataset = "enterprise"
        else:
            dataset = "core"

        key = (ats, row["slug"].casefold())
        existing = catalogs[dataset].get(key)

        if existing is None:
            catalogs[dataset][key] = row
        elif not existing["source_url"] and row["source_url"]:
            existing["source_url"] = row["source_url"]

    result = {}

    for dataset, values in catalogs.items():
        result[dataset] = sorted(
            values.values(),
            key=lambda row: (row["ats"], row["name"].casefold()),
        )

    keysets = {
        dataset: {(row["ats"], row["slug"].casefold()) for row in result[dataset]}
        for dataset in result
    }
    datasets = list(keysets)

    for i, left in enumerate(datasets):
        for right in datasets[i + 1 :]:
            overlap = keysets[left] & keysets[right]

            if overlap:
                raise ValueError(
                    f"catalog overlap between {left} and {right}: "
                    f"{sorted(overlap)[:3]}"
                )

    return result


def render(rows: list[dict]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    catalogs = consolidate(read_sources())

    if sum(len(rows) for rows in catalogs.values()) < 20_000:
        raise ValueError("refusing to emit an unexpectedly small catalog")

    changed = []

    for dataset, rows in catalogs.items():
        path = OUTPUT_PATHS[dataset]
        content = render(rows)

        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""

            if current != content:
                changed.append(path.name)
        else:
            path.write_text(content, encoding="utf-8")

    if args.check and changed:
        print(f"Out of date: {', '.join(changed)}")
        return 1

    action = "Verified" if args.check else "Wrote"
    print(
        f"{action} {len(catalogs['core']):,} core ATS boards, "
        f"{len(catalogs['enterprise']):,} enterprise ATS boards, and "
        f"{len(catalogs['direct']):,} company-owned boards"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
