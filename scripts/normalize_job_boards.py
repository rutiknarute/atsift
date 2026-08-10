"""Normalize the rich job-board reference CSV into a scan-ready dataset.

The source keeps discovery metadata (`api_url`, method, status, and notes).
This script converts each row to the scanner's `name,ats,slug,source_url`
contract while applying the live-verified corrections discovered during the
August 2026 audit.

    python3 scripts/normalize_job_boards.py
    python3 scripts/normalize_job_boards.py --check
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

DEFAULT_SOURCE = BASE_DIR / "data/job_boards_reference.csv"
DEFAULT_OUTPUT = BASE_DIR / "data/companies_reference.csv"
FIELDS = ["name", "ats", "slug", "source_url"]

# Candidate tokens and wrapper sites that cannot be copied literally. Every
# target below was checked against the canonical list and detail endpoints.
OVERRIDES = {
    "DigitalOcean": (
        "DigitalOcean",
        "greenhouse",
        "digitalocean98",
    ),
    "Guild": ("Guild", "greenhouse", "guild"),
    "HubSpot": ("HubSpot", "greenhouse", "hubspotjobs"),
    "TRM Labs": ("TRM Labs", "ashby", "trm-labs"),
    "Zipline": ("Zipline", "greenhouse", "flyzipline"),
    "Lenovo": (
        "Lenovo",
        "avature",
        "https://jobs.lenovo.com/en_US/careers",
    ),
    "Lyft": ("Lyft", "greenhouse", "lyft"),
    "GitHub": (
        "GitHub",
        "jibe",
        "https://githubinc.jibeapply.com",
    ),
    "Dell": (
        "Dell",
        "oracle",
        (
            "https://enterpriseplatform.dell.com/hcmUI/"
            "CandidateExperience/en/sites/careers"
        ),
    ),
    # hdpc.fa.us2.oraclecloud.com is HDFC Bank's lateral-hiring tenant; the
    # source row's "Home Depot" label is incorrect.
    "Home Depot": (
        "HDFC Bank",
        "oracle",
        (
            "https://hdpc.fa.us2.oraclecloud.com/hcmUI/"
            "CandidateExperience/en/sites/LateralHiring"
        ),
    ),
    "JPMorgan Chase": (
        "JPMorgan Chase",
        "oracle",
        (
            "https://jpmc.fa.oraclecloud.com/hcmUI/"
            "CandidateExperience/en/sites/CX_1001"
        ),
    ),
    "CVS Health": (
        "CVS Health",
        "workday",
        "https://cvshealth.wd1.myworkdayjobs.com/CVS_Health_Careers",
    ),
    "Walmart": (
        "Walmart",
        "workday",
        "https://walmart.wd504.myworkdayjobs.com/WalmartExternal",
    ),
    "AT&T": (
        "AT&T",
        "workday",
        "https://att.wd1.myworkdayjobs.com/ATTGeneral",
    ),
    "Citi": (
        "Citi",
        "workday",
        "https://citi.wd5.myworkdayjobs.com/2",
    ),
    "HP": (
        "HP",
        "workday",
        "https://hp.wd5.myworkdayjobs.com/ExternalCareerSite",
    ),
    "Samsung": (
        "Samsung",
        "workday",
        "https://sec.wd3.myworkdayjobs.com/Samsung_Careers",
    ),
    "Sony": (
        "Sony",
        "workday",
        "https://sonyglobal.wd1.myworkdayjobs.com/SonyGlobalCareers",
    ),
}


def normalize(row: dict) -> dict:
    company = str(row.get("company") or "").strip()
    source_url = str(row.get("board_url") or "").strip()

    if company in OVERRIDES:
        name, ats, slug = OVERRIDES[company]
    else:
        ats = str(row.get("ats") or "").strip().lower()
        token = str(row.get("token") or "").strip()

        if ats not in {"ashby", "greenhouse", "lever"} or not token:
            raise ValueError(f"no normalization rule for {company!r} ({ats})")

        name, slug = company, token

    if ats not in SUPPORTED_ATS:
        raise ValueError(f"unsupported target ATS for {company!r}: {ats}")

    return {
        "name": name,
        "ats": ats,
        "slug": slug,
        "source_url": source_url,
    }


def read_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    required = {
        "company",
        "ats",
        "token",
        "board_url",
        "api_url",
        "api_method",
        "status",
        "notes",
    }
    missing = required - set(rows[0] if rows else {})

    if missing:
        raise ValueError(f"reference CSV is missing columns: {sorted(missing)}")

    return rows


def render(rows: list[dict]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(normalize(row) for row in rows)

    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rows = read_rows(args.source)
    content = render(rows)

    if args.check:
        current = (
            args.output.read_text(encoding="utf-8")
            if args.output.exists()
            else ""
        )

        if current != content:
            print(f"Out of date: {args.output.relative_to(BASE_DIR)}")
            return 1

        print(f"Verified {len(rows)} normalized boards in {args.output.name}")
        return 0

    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote {len(rows)} normalized boards to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
