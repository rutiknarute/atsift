"""
Convert the preserved v1 snapshot into the schema the rebuild uses.

The old snapshot is a bare list with different field names (source, job_url,
first_published_at). Everything the new UI reads is derivable from it, so the
491 already-analysed postings carry over rather than being rescanned.

    python3 scripts/migrate_snapshot.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scanner.boolean_search import ROLE_CATEGORY_LABELS  # noqa: E402
from scanner.dates import age_hours, iso, parse_timestamp  # noqa: E402

SOURCE = BASE_DIR / "data" / "jobs-snapshot.json"
TARGET = BASE_DIR / "web" / "src" / "server" / "jobs-snapshot.json"


def convert(record: dict) -> dict:
    posted_raw = record.get("first_published_at") or record.get(
        "source_updated_at"
    )
    posted = parse_timestamp(posted_raw)
    categories = [
        c for c in (record.get("categories") or []) if c in ROLE_CATEGORY_LABELS
    ]

    return {
        "uid": record.get("uid") or "",
        "ats": record.get("source") or "",
        "company": record.get("company") or "",
        "company_slug": record.get("slug") or "",
        "job_id": str(record.get("id") or ""),
        "title": (record.get("title") or "").strip(),
        "url": record.get("job_url") or record.get("apply_url") or "",
        "location": record.get("location") or "",
        "team": record.get("team") or "",
        "posted_at": posted.isoformat() if posted else None,
        "age_hours": age_hours(posted_raw),
        "description": "",
        "salary_context": "",
        "categories": categories,
        "category_labels": [ROLE_CATEGORY_LABELS[c] for c in categories],
        "analysis": record.get("analysis") or None,
        "viewed": bool(record.get("viewed_at")),
    }


def main() -> int:
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))

    if not isinstance(raw, list):
        print("Unexpected snapshot shape: expected a list.")
        return 1

    jobs = [convert(record) for record in raw if isinstance(record, dict)]
    jobs = [job for job in jobs if job["uid"] and job["title"]]
    jobs.sort(key=lambda job: job.get("age_hours") or 1e9)

    newest = min(
        (job["age_hours"] for job in jobs if job["age_hours"] is not None),
        default=None,
    )

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(
            {
                "jobs": jobs,
                "scanned_at": iso(),
                "source": "packaged-snapshot",
                "count": len(jobs),
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    analysed = sum(1 for job in jobs if job.get("analysis"))

    print(f"Wrote {len(jobs)} jobs to {TARGET.relative_to(BASE_DIR)}")
    print(f"  with analysis: {analysed}")
    print(f"  newest posting: {newest:.0f}h old" if newest else "  no dates")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
