"""
Merge a `name,ats,slug` list into the company catalogs.

Each row is routed by its board — the five token-slug boards to
`companies.csv`, Workday to `companies_workday.csv`, and anything no adapter
covers to `companies_plus.csv` — so an unknown ATS is parked instead of
silently dropped. Rows already present under the same ats + slug are skipped,
matching how the catalogs were deduplicated in the first place.

`--verify` extends that to the board itself: a row whose named board does not
answer is parked in "plus" too, rather than being re-homed onto whichever ATS
does answer. A company is filed where the list says it is, or it is filed as
unresolved — never quietly moved. This upholds the catalogs' promise that
every row was live-checked, so prefer it whenever the source is untrusted.

    python3 scripts/import_companies.py incoming.csv [more.csv ...]
    python3 scripts/import_companies.py --verify incoming.csv
    python3 scripts/import_companies.py --dry-run incoming.csv
"""

from __future__ import annotations

import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scanner.ats import fetch_company  # noqa: E402
from scanner.companies import dataset_for_ats  # noqa: E402
from scanner.config import COMPANY_DATASET_PATHS, MAX_WORKERS  # noqa: E402
from scanner.http import BoardUnavailable  # noqa: E402

FIELDS = ["name", "ats", "slug"]


def board_resolves(row: dict) -> bool:
    """
    Does this company's named board answer at all?

    The real adapter does the asking, so a slug is checked exactly the way a
    scan would use it. An empty board still counts — a company with no open
    roles today is not a bad row. Only BoardUnavailable, which is the 404 the
    adapters raise for a retired or misspelt slug, condemns it.

    One blind spot worth knowing: SmartRecruiters answers 200 with zero
    postings for any string, so a SmartRecruiters row with no open roles
    passes here without really having been proven.
    """

    try:
        fetch_company(row)
    except BoardUnavailable:
        return False
    except Exception:
        # A transport hiccup is not evidence the board is gone; keep the row
        # where the list put it rather than condemning it on a flaky request.
        return True

    return True


def read_catalog(path: Path) -> list[dict]:
    if not path.exists():
        return []

    with open(path, newline="", encoding="utf-8") as handle:
        return [
            {field: str(row.get(field) or "").strip() for field in FIELDS}
            for row in csv.DictReader(handle)
        ]


def write_catalog(path: Path, rows: list[dict]) -> None:
    # The catalogs are grouped by ATS and sorted by name within the group, so
    # a merge stays reviewable as a diff instead of reordering the file.
    rows.sort(key=lambda row: (row["ats"], row["name"].casefold()))

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    verify = "--verify" in argv
    sources = [Path(arg) for arg in argv if not arg.startswith("-")]

    if not sources:
        print(__doc__.strip())
        return 1

    incoming: list[dict] = []

    for source in sources:
        if not source.exists():
            print(f"No such file: {source}")
            return 1

        with open(source, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                name = str(row.get("name") or "").strip()
                ats = str(row.get("ats") or "").strip().lower()
                slug = str(row.get("slug") or "").strip()

                if name and ats and slug:
                    incoming.append({"name": name, "ats": ats, "slug": slug})

    catalogs = {
        dataset: read_catalog(path)
        for dataset, path in COMPANY_DATASET_PATHS.items()
    }
    # A slug is only unique per board, and the same company can legitimately
    # sit in two catalogs, so dedup is scoped to the catalog being written.
    seen = {
        dataset: {(row["ats"], row["slug"].casefold()) for row in rows}
        for dataset, rows in catalogs.items()
    }

    added: dict[str, list[dict]] = {dataset: [] for dataset in catalogs}
    unresolved: list[dict] = []
    evicted: list[tuple[str, dict]] = []
    skipped = 0

    resolves: dict[int, bool] = {}

    if verify:
        print(f"Verifying {len(incoming)} boards...")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            checked = pool.map(board_resolves, incoming)
            resolves = {id(row): ok for row, ok in zip(incoming, checked)}

    for row in incoming:
        dataset = dataset_for_ats(row["ats"])

        # A board that does not answer is parked, not re-homed: the row keeps
        # the ATS the list claimed, so the disagreement stays visible.
        key = (row["ats"], row["slug"].casefold())

        if verify and dataset != "plus" and not resolves[id(row)]:
            # A row already catalogued as scannable but now dead has to leave
            # that catalog, not merely gain a copy in "plus" — otherwise the
            # scan keeps requesting a slug we just proved is gone.
            if key in seen[dataset]:
                catalogs[dataset] = [
                    kept
                    for kept in catalogs[dataset]
                    if (kept["ats"], kept["slug"].casefold()) != key
                ]
                seen[dataset].discard(key)
                evicted.append((dataset, row))

            dataset = "plus"
            unresolved.append(row)

        if key in seen[dataset]:
            skipped += 1
            continue

        seen[dataset].add(key)
        catalogs[dataset].append(row)
        added[dataset].append(row)

    print(f"Read {len(incoming)} rows from {len(sources)} file(s)")

    for dataset, rows in added.items():
        path = COMPANY_DATASET_PATHS[dataset].relative_to(BASE_DIR)
        boards = sorted({row["ats"] for row in rows})
        detail = f" — {' · '.join(boards)}" if boards else ""

        print(
            f"  {dataset:<8} +{len(rows):<4} "
            f"→ {len(catalogs[dataset]):>6} rows  {path}{detail}"
        )

    print(f"  already present: {skipped}")

    for row in unresolved:
        print(
            f"  unresolved: {row['name']} — no {row['ats']} board at "
            f"{row['slug']!r}, parked in plus"
        )

    for dataset, row in evicted:
        print(f"  evicted from {dataset}: {row['name']} — board is gone")

    if dry_run:
        print("Dry run — nothing written.")
        return 0

    touched = {dataset for dataset, _ in evicted}

    for dataset, rows in catalogs.items():
        changed = added[dataset] or dataset in touched

        if changed or not COMPANY_DATASET_PATHS[dataset].exists():
            write_catalog(COMPANY_DATASET_PATHS[dataset], rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
