"""
Backend tests.

Focused on the logic that decides what the product returns — the boolean
search, the time window, and US screening. Network adapters are covered by
shape tests, not live calls.

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.boolean_search import title_categories, title_matches_keywords
from scanner.dates import parse_timestamp, within_window
from scanner.locations import screen_location
from scanner.records import dedupe_jobs, job_uid, make_job
from scanner.scan import clamp_lookback


# --- Boolean search ---------------------------------------------------------


class TestBooleanSearch:
    def test_matches_expected_categories(self):
        assert title_categories("Software Engineer, New Grad") == [
            "software",
            "new_grad",
        ]

    def test_excludes_seniority(self):
        for title in (
            "Senior Software Engineer",
            "Staff Data Engineer",
            "Principal Architect",
            "Engineering Manager",
            "Director of Data",
            "VP Engineering",
        ):
            assert not title_matches_keywords(title), title

    def test_boundary_safety(self):
        """The false positives plain substring matching would produce."""

        for title in (
            "Build Engineer",       # UI must not match "build"
            "SRE",                  # sr must not match "SRE"
            "Leaderboard Engineer",  # lead must not match "leaderboard"
            "Forms Specialist",     # MS must not match "forms"
            "Upgrade Specialist",   # grad must not match "upgrade"
        ):
            assert not title_matches_keywords(title), title

    def test_gtm_excludes_recruiter_not_architect(self):
        assert not title_categories("Growth Recruiter")
        assert "gtm" in title_categories("Growth Architect")

    def test_category_filter_is_respected(self):
        assert title_categories("Data Analyst", ["software"]) == []
        assert title_categories("Data Analyst", ["data_analyst"]) == [
            "data_analyst"
        ]

    def test_empty_title(self):
        assert title_categories(None) == []
        assert title_categories("") == []


# --- Time window ------------------------------------------------------------


class TestWindow:
    def test_recent_posting_is_inside(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=2)
        assert within_window(recent.isoformat(), 24)

    def test_old_posting_is_outside(self):
        old = datetime.now(timezone.utc) - timedelta(hours=200)
        assert not within_window(old.isoformat(), 72)

    def test_undated_posting_is_excluded(self):
        """No date means we cannot honour the window, so it does not count."""

        assert not within_window(None, 24)
        assert not within_window("", 24)

    def test_epoch_milliseconds(self):
        """Lever returns epoch ms."""

        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        assert within_window(now_ms, 1)

    def test_naive_timestamp_is_treated_as_utc(self):
        parsed = parse_timestamp("2026-01-01 12:00:00")
        assert parsed is not None and parsed.tzinfo is not None

    def test_clamp_respects_ceiling(self):
        assert clamp_lookback(1000) == 72
        assert clamp_lookback(-5) == 24
        assert clamp_lookback("nonsense") == 24
        assert clamp_lookback(48) == 48


# --- Locations --------------------------------------------------------------


class TestLocations:
    def test_clear_us(self):
        for value in (
            "New York, NY",
            "Austin, TX 78701",
            "Boston, Massachusetts",
            "United States",
            "Remote - US",
            "San Francisco",
        ):
            assert screen_location(value) == "US", value

    def test_clear_non_us(self):
        for value in (
            "London, UK",
            "Bangalore, India",
            "Toronto, Canada",
            "Paris, France",
            "EMEA",
        ):
            assert screen_location(value) == "NON_US", value

    def test_multi_region_including_us_counts_as_us(self):
        assert screen_location("Remote (US or Canada)") == "US"

    def test_ambiguous_goes_to_the_llm(self):
        assert screen_location("Remote") == "AMBIGUOUS"
        assert screen_location("") == "AMBIGUOUS"


# --- Records ----------------------------------------------------------------


class TestRecords:
    def test_uid_shape(self):
        assert job_uid("ashby", "acme", "123") == "ashby:acme:123"

    def test_make_job_populates_labels(self):
        job = make_job(
            ats="greenhouse",
            company="Acme",
            company_slug="acme",
            job_id=1,
            title="Software Engineer",
            url="https://example.com",
            categories=["software"],
        )

        assert job["uid"] == "greenhouse:acme:1"
        assert job["category_labels"] == ["Software"]

    def test_dedupe_keeps_first(self):
        jobs = [
            {"uid": "a", "title": "first"},
            {"uid": "a", "title": "second"},
            {"uid": "b", "title": "third"},
        ]

        result = dedupe_jobs(jobs)

        assert len(result) == 2
        assert result[0]["title"] == "first"
