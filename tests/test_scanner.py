"""
Backend tests.

Focused on the logic that decides what the product returns — the boolean
search, the time window, and US screening. Network adapters are covered by
shape tests, not live calls.

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

import csv
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scanner.logos as logos
from scanner.boolean_search import title_categories, title_matches_keywords
from scanner.analysis import (
    analysis_description,
    fallback_analysis,
    normalize_analysis,
)
from scanner.ats import (
    SUPPORTED_ATS,
    apple,
    atlassian,
    ashby,
    avature,
    greenhouse,
    ibm,
    icims,
    jibe,
    lever,
    oracle,
    rippling,
    smartrecruiters,
    successfactors,
    workday,
)
from scanner.companies import (
    CORE_ATS,
    DIRECT_ATS,
    ENTERPRISE_ATS,
    dataset_for_ats,
    dataset_summary,
    load_companies,
    resolve_dataset,
)
from scanner.config import (
    DEFAULT_LOOKBACK_HOURS,
    LOOKBACK_OPTIONS,
    MAX_LOOKBACK_HOURS,
)
from scanner.experience import (
    extract_required_experience,
    minimum_years_from_text,
    resolve_experience,
)
from scanner.dates import parse_timestamp, within_window
from scanner.locations import (
    job_has_confirmed_us_location,
    screen_location,
)
from scanner.records import dedupe_jobs, job_uid, make_job
from scanner.scan import _confirmed, clamp_lookback


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

    def test_every_offered_window_survives_clamping(self):
        # A window the UI offers must come back unchanged, or the scan would
        # sweep a different period than the one the user picked and froze.
        for hours in LOOKBACK_OPTIONS:
            assert clamp_lookback(hours) == float(hours)

    def test_short_windows_are_offered_and_ordered(self):
        assert LOOKBACK_OPTIONS[:3] == [1, 2, 4]
        assert LOOKBACK_OPTIONS == sorted(LOOKBACK_OPTIONS)
        assert max(LOOKBACK_OPTIONS) == MAX_LOOKBACK_HOURS
        assert DEFAULT_LOOKBACK_HOURS in LOOKBACK_OPTIONS

    def test_one_hour_window_cuts_at_one_hour(self):
        now = datetime.now(timezone.utc)

        assert within_window((now - timedelta(minutes=30)).isoformat(), 1)
        assert not within_window((now - timedelta(minutes=90)).isoformat(), 1)
        assert within_window((now - timedelta(minutes=90)).isoformat(), 2)
        assert not within_window((now - timedelta(hours=5)).isoformat(), 4)


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

    def test_ambiguous_job_requires_positive_analysis(self):
        unresolved = {
            "location": "Remote",
            "location_verdict": "AMBIGUOUS",
        }
        confirmed = {
            **unresolved,
            "analysis": {"us_location_eligible": "YES"},
        }

        assert not job_has_confirmed_us_location(unresolved)
        assert job_has_confirmed_us_location(confirmed)

    def test_structured_us_job_does_not_require_analysis(self):
        assert job_has_confirmed_us_location(
            {
                "location": "Austin, TX",
                "location_verdict": "US",
            }
        )


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


# --- Company catalogs -------------------------------------------------------


class TestCompanyCatalogs:
    def test_rich_job_board_reference_preserves_every_source_field(self):
        path = Path(__file__).resolve().parent.parent
        path /= "data/job_boards_reference.csv"

        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)

        assert reader.fieldnames == [
            "company",
            "ats",
            "token",
            "site",
            "host",
            "board_url",
            "api_url",
            "api_method",
            "status",
            "notes",
        ]
        assert len(rows) == 77
        assert len({row["company"] for row in rows}) == 77
        assert sum(row["status"] == "confirmed" for row in rows) == 48
        assert sum(row["status"] == "unverified" for row in rows) == 26
        assert sum(row["status"] == "needs_site_number" for row in rows) == 3

    def test_priority_source_ledger_preserves_all_submitted_rows(self):
        path = Path(__file__).resolve().parent.parent
        path /= "data/companies_priority.csv"

        with open(path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        assert len(rows) == 154
        assert all(row["source_url"].startswith("https://") for row in rows)
        assert sum(
            row["source_url"]
            == "https://job-boards.greenhouse.io/pendo/jobs/"
            for row in rows
        ) == 2
        assert sum(
            row["source_url"] == "https://careers.amd.com/careers-home/jobs/"
            for row in rows
        ) == 2
        assert sum(
            row["slug"]
            == "https://sonyglobal.wd1.myworkdayjobs.com/SonyGlobalCareers"
            for row in rows
        ) == 2
        assert [
            (row["name"], row["ats"], row["slug"], row["source_url"])
            for row in rows[-18:]
        ] == [
            (
                "Lyft",
                "greenhouse",
                "lyft",
                "https://app.careerpuck.com/job-board/lyft/job/",
            ),
            (
                "Lenovo",
                "avature",
                "https://jobs.lenovo.com/en_US/careers",
                "https://jobs.lenovo.com/en_US/careers/JobDetail?",
            ),
            (
                "Palantir",
                "lever",
                "palantir",
                "https://jobs.lever.co/palantir/",
            ),
            (
                "Sony",
                "workday",
                "https://sonyglobal.wd1.myworkdayjobs.com/SonyGlobalCareers",
                (
                    "https://sonyglobal.wd1.myworkdayjobs.com/en-US/"
                    "SonyGlobalCareers/job/"
                ),
            ),
            (
                "HP",
                "workday",
                "https://hp.wd5.myworkdayjobs.com/ExternalCareerSite",
                "https://hp.wd5.myworkdayjobs.com/ExternalCareerSite/job/",
            ),
            (
                "Dropbox",
                "greenhouse",
                "dropbox",
                "https://www.dropbox.jobs/en/jobs",
            ),
            (
                "Sony",
                "workday",
                "https://sonyglobal.wd1.myworkdayjobs.com/SonyGlobalCareers",
                (
                    "https://sonyglobal.wd1.myworkdayjobs.com/"
                    "SonyGlobalCareers/job/"
                ),
            ),
            (
                "Dell",
                "oracle",
                (
                    "https://enterpriseplatform.dell.com/hcmUI/"
                    "CandidateExperience/en/sites/careers"
                ),
                (
                    "https://enterpriseplatform.dell.com/hcmUI/"
                    "CandidateExperience/en/sites/careers/job/"
                ),
            ),
            (
                "CVS Health",
                "workday",
                (
                    "https://cvshealth.wd1.myworkdayjobs.com/"
                    "CVS_Health_Careers"
                ),
                (
                    "https://jobs.cvshealth.com/us/en/job/"
                    "CVSCHLUSR0954957EXTERNALENUS/"
                ),
            ),
            (
                "Walmart",
                "workday",
                "https://walmart.wd504.myworkdayjobs.com/WalmartExternal",
                "https://careers.walmart.com/us/en/jobs/",
            ),
            (
                "GitHub",
                "jibe",
                "https://githubinc.jibeapply.com",
                "https://githubinc.jibeapply.com/jobs/",
            ),
            (
                "JPMorgan Chase",
                "oracle",
                (
                    "https://jpmc.fa.oraclecloud.com/hcmUI/"
                    "CandidateExperience/en/sites/CX_1001"
                ),
                (
                    "https://jpmc.fa.oraclecloud.com/hcmUI/"
                    "CandidateExperience/en/sites/"
                ),
            ),
            (
                "HDFC Bank",
                "oracle",
                (
                    "https://hdpc.fa.us2.oraclecloud.com/hcmUI/"
                    "CandidateExperience/en/sites/LateralHiring"
                ),
                (
                    "https://hdpc.fa.us2.oraclecloud.com/hcmUI/"
                    "CandidateExperience/en/sites/LateralHiring/job/"
                ),
            ),
            (
                "Scale AI",
                "greenhouse",
                "scaleai",
                "https://job-boards.greenhouse.io/scaleai/jobs/",
            ),
            (
                "Samsung",
                "workday",
                "https://sec.wd3.myworkdayjobs.com/Samsung_Careers",
                "https://sec.wd3.myworkdayjobs.com/Samsung_Careers/job/",
            ),
            (
                "Spotify",
                "lever",
                "spotify",
                "https://jobs.lever.co/spotify/",
            ),
            (
                "AT&T",
                "workday",
                "https://att.wd1.myworkdayjobs.com/ATTGeneral",
                "https://www.att.jobs/job/-/",
            ),
            (
                "Citi",
                "workday",
                "https://citi.wd5.myworkdayjobs.com/2",
                "https://jobs.citi.com/job/-/-/",
            ),
        ]

    def test_supported_boards_route_to_their_catalog(self):
        for ats in CORE_ATS:
            assert dataset_for_ats(ats) == "core"

        for ats in ENTERPRISE_ATS:
            assert dataset_for_ats(ats) == "enterprise"

        for ats in DIRECT_ATS:
            assert dataset_for_ats(ats) == "direct"

    def test_unadapted_boards_route_to_plus(self):
        # The point of "plus": a board nothing can read is parked, not lost.
        for ats in ("taleo", "comeet", "", None):
            assert dataset_for_ats(ats) == "plus"

    def test_routing_ignores_case_and_padding(self):
        assert dataset_for_ats("  Greenhouse ") == "core"
        assert dataset_for_ats("WORKDAY") == "enterprise"
        assert dataset_for_ats(" Apple ") == "direct"

    def test_unknown_dataset_falls_back_to_core(self):
        assert resolve_dataset("nope") == "core"
        assert resolve_dataset(None) == "core"
        assert resolve_dataset("enterprise") == "enterprise"
        assert resolve_dataset("direct") == "direct"
        assert resolve_dataset("plus") == "plus"
        assert resolve_dataset("priority") == "priority"
        assert resolve_dataset("reference") == "reference"

    def test_only_the_three_authoritative_catalogs_are_selectable(self):
        assert dataset_summary() == [
            {
                "id": "core",
                "label": (
                    "Core ATS boards · Ashby, Greenhouse, Lever, "
                    "SmartRecruiters, Workable & Rippling"
                ),
                "count": 19_360,
            },
            {
                "id": "enterprise",
                "label": "Enterprise ATS boards · Workday, iCIMS, Oracle & more",
                "count": 6_793,
            },
            {
                "id": "direct",
                "label": "Company-owned career sites",
                "count": 3,
            },
        ]

    def test_reference_catalog_normalizes_all_77_boards(self):
        companies = load_companies("reference")
        mapped = {
            company["name"]: (company["ats"], company["slug"])
            for company in companies
        }

        assert len(companies) == 77
        assert len({(company["ats"], company["slug"]) for company in companies}) == 77
        assert all(company["ats"] in SUPPORTED_ATS for company in companies)
        assert all(company.get("source_url") for company in companies)
        assert mapped["DigitalOcean"] == ("greenhouse", "digitalocean98")
        assert mapped["Guild"] == ("greenhouse", "guild")
        assert mapped["HubSpot"] == ("greenhouse", "hubspotjobs")
        assert mapped["TRM Labs"] == ("ashby", "trm-labs")
        assert mapped["Zipline"] == ("greenhouse", "flyzipline")
        assert mapped["HDFC Bank"] == (
            "oracle",
            (
                "https://hdpc.fa.us2.oraclecloud.com/hcmUI/"
                "CandidateExperience/en/sites/LateralHiring"
            ),
        )

    def test_priority_catalog_keeps_every_unique_submitted_board(self):
        companies = load_companies("priority")

        assert len(companies) == 130
        assert all(company.get("source_url") for company in companies)
        assert {
            (company["name"], company["ats"], company["slug"])
            for company in companies
            if company["name"] in {
                "AMD",
                "Apple",
                "Atlassian",
                "IBM",
                "Lenovo",
                "Opendoor",
                "SAP",
                "Whatnot",
            }
        } == {
            ("AMD", "jibe", "https://careers.amd.com"),
            ("Apple", "apple", "apple"),
            (
                "Atlassian",
                "atlassian",
                "https://www.atlassian.com/endpoint/careers/listings",
            ),
            ("IBM", "ibm", "ibm"),
            (
                "Lenovo",
                "avature",
                "https://jobs.lenovo.com/en_US/careers",
            ),
            ("Opendoor", "rippling", "opendoor"),
            ("SAP", "successfactors", "https://jobs.sap.com"),
            ("Whatnot", "ashby", "whatnot"),
        }

    def test_rippling_catalog_has_two_thousand_distinct_live_entries(self):
        companies = tuple(
            company
            for company in load_companies("core")
            if company["ats"] == "rippling"
        )
        names = {company["name"].casefold() for company in companies}
        slugs = {company["slug"].casefold() for company in companies}

        assert len(companies) >= 2_000
        assert len(names) == len(companies)
        assert len(slugs) == len(companies)
        assert all(company["ats"] == "rippling" for company in companies)
        assert all(
            company.get("source_url")
            == f"https://ats.rippling.com/{company['slug']}/jobs"
            for company in companies
        )
        assert all(
            company["name"][0].isalnum()
            and "<" not in company["name"]
            and ">" not in company["name"]
            for company in companies
        )

    def test_icims_catalog_has_five_thousand_verified_production_portals(self):
        companies = tuple(
            company
            for company in load_companies("enterprise")
            if company["ats"] == "icims"
        )

        assert len(companies) == 5_685
        assert len({company["slug"] for company in companies}) == len(companies)
        assert all(company["slug"].endswith(".icims.com") for company in companies)
        assert all(
            company.get("source_url")
            == f"https://{company['slug']}/jobs/search?ss=1"
            for company in companies
        )
        assert all(
            not company["name"].casefold().startswith("(old)")
            for company in companies
        )
        assert all(
            "<" not in company["name"] and ">" not in company["name"]
            for company in companies
        )

    def test_icims_reference_preserves_live_metadata_and_rejections(self):
        data_dir = Path(__file__).resolve().parent.parent / "data"

        with (data_dir / "icims_boards_reference.csv").open(
            newline="",
            encoding="utf-8",
        ) as handle:
            reference = list(csv.DictReader(handle))

        with (data_dir / "icims_discovery_audit.csv").open(
            newline="",
            encoding="utf-8",
        ) as handle:
            audit = list(csv.DictReader(handle))

        assert len(reference) == 5_714
        assert sum(row["production_eligible"] == "True" for row in reference) == 5_685
        assert sum(row["us_evidence"] == "True" for row in reference) == 2_549
        assert len({row["company_key"] for row in reference}) == 1_990
        assert len(audit) == 11_739
        assert sum(row["accepted"] == "True" for row in audit) == 5_714

    def test_scannable_catalogs_hold_only_their_own_boards(self):
        for dataset in ("core", "enterprise", "direct"):
            for company in load_companies(dataset):
                assert dataset_for_ats(company["ats"]) == dataset

    def test_direct_catalog_is_only_the_three_company_owned_sources(self):
        companies = load_companies("direct")

        assert {
            (company["name"], company["ats"], company["slug"])
            for company in companies
        } == {
            ("Apple", "apple", "apple"),
            ("IBM", "ibm", "ibm"),
            (
                "Atlassian",
                "atlassian",
                "https://www.atlassian.com/endpoint/careers/listings",
            ),
        }

    def test_plus_never_shadows_a_scannable_row(self):
        # "plus" holds unscannable rows — a board with no adapter, or one
        # that named an adapter but did not answer — plus a handful of
        # hand-verified extras not yet folded into the active catalogs. None
        # of it may
        # also sit in a scannable catalog, or one company would be scanned
        # under a slug already known to be dead (or double-counted).
        scannable = {
            (company["ats"], company["slug"].casefold())
            for dataset in ("core", "enterprise", "direct")
            for company in load_companies(dataset)
        }

        for company in load_companies("plus"):
            key = (company["ats"], company["slug"].casefold())

            assert key not in scannable


# --- Experience extraction -------------------------------------------------


class TestExperience:
    def test_common_ranges_and_compact_values(self):
        assert minimum_years_from_text("2-5 years") == 2
        assert minimum_years_from_text("1–2 years") == 1
        assert minimum_years_from_text("7-10") == 7
        assert minimum_years_from_text(">=3") == 3
        assert minimum_years_from_text("At least six months") == 0.5

    def test_multiple_required_thresholds_use_strongest_floor(self):
        requirement = (
            "3+ years of production experience, with 1–2+ years "
            "focused on LLM-powered or agentic products."
        )

        assert minimum_years_from_text(requirement) == 3

    def test_or_paths_use_lowest_satisfying_floor(self):
        requirement = (
            "Bachelor's degree with 5 years of experience, or a "
            "Master's degree with two years of experience."
        )

        assert minimum_years_from_text(requirement) == 2

    def test_html_line_break_or_paths_remain_alternatives(self):
        extracted = extract_required_experience(
            "BS with 5+ years of professional experience"
            "<br>OR<br>"
            "MS with 3+ years of professional experience"
        )

        assert extracted.minimum_years == 3

    def test_preferred_experience_is_not_treated_as_required(self):
        extracted = extract_required_experience(
            "Required: 2+ years of software experience.\n"
            "Nice to have: 7+ years of healthcare experience."
        )

        assert extracted.minimum_years == 2
        assert "2+ years" in extracted.text

    def test_html_is_removed_from_experience_evidence(self):
        extracted = extract_required_experience(
            "<ul><li><strong>Required:</strong> 3+ years of "
            "software experience.</li></ul>"
        )

        assert extracted.minimum_years == 3
        assert "<" not in extracted.text

    def test_qualifications_repair_junk_model_answer(self):
        resolved = resolve_experience(
            experience_text="Yes",
            model_minimum=None,
            qualifications=(
                "3+ years of production experience, with 1–2+ years "
                "focused on LLM-powered products."
            ),
        )

        assert resolved.minimum_years == 3
        assert resolved.text.startswith("3+ years")

    def test_compact_model_values_receive_a_unit(self):
        assert resolve_experience(
            experience_text="7-10",
            model_minimum=None,
        ).text == "7–10 years"
        assert resolve_experience(
            experience_text="2+",
            model_minimum=None,
        ).text == "2+ years"

    def test_evidence_overrides_contradictory_model_number(self):
        normalized = normalize_analysis(
            {
                "us_location_eligible": "YES",
                "opt_eligible": "YES",
                "opt_blocking_line": "",
                "degree": "Not clearly stated.",
                "qualifications": "3+ years of production experience.",
                "eligibility": "Not clearly stated.",
                "key_tech_skills": [],
                "experience_years": "3+ years",
                "minimum_years": 1,
                "ats_keywords": [],
                "tip": "Tailor the resume.",
                "salary": "Not listed.",
                "team": "Engineering",
            }
        )

        assert normalized["minimum_years"] == 3
        assert normalized["experience_years"] == "3+ years"

    def test_jd_alternative_overrides_incomplete_model_summary(self):
        resolved = resolve_experience(
            experience_text="5+ years",
            model_minimum=5,
            degree=(
                "BS with 5+ years of professional experience OR "
                "MS with 3+ years of professional experience"
            ),
            description=(
                "BS with 5+ years of professional experience"
                "<br>OR<br>"
                "MS with 3+ years of professional experience"
            ),
        )

        assert resolved.minimum_years == 3
        assert "OR" in resolved.text

    def test_long_description_keeps_requirement_evidence(self):
        description = (
            "Company background. " * 800
            + "\nRequired qualifications: 4+ years of software experience."
        )
        bounded = analysis_description(description)

        assert len(bounded) <= 8_000
        assert "4+ years of software experience" in bounded

    def test_years_still_extract_when_model_is_unavailable(self):
        fallback = fallback_analysis(
            {
                "description": (
                    "Required qualifications: 2+ years of professional "
                    "software experience."
                )
            }
        )

        assert fallback["analysis_failed"] is True
        assert fallback["minimum_years"] == 2
        assert fallback["experience_years"].startswith("Required")

    def test_fallback_extracts_complete_jd_details(self):
        fallback = fallback_analysis(
            {
                "description": (
                    "Bachelor's degree in Computer Science required. "
                    "You have 2+ years of software experience using "
                    "Python, React, AWS, and SQL. "
                    "Candidates must work without sponsorship. "
                    "Compensation is $120,000-$145,000 per year."
                ),
                "team": "Platform Engineering",
            }
        )

        serialized = " ".join(
            str(value) for value in fallback.values()
        ).casefold()

        assert fallback["opt_eligible"] == "NO"
        assert "bachelor" in fallback["degree"].casefold()
        assert fallback["minimum_years"] == 2
        assert {"Python", "React", "AWS", "SQL"}.issubset(
            fallback["key_tech_skills"]
        )
        assert "$120,000" in fallback["salary"]
        assert fallback["team"] == "Platform Engineering"
        assert "unavailable" not in serialized


# --- Incremental publishing ------------------------------------------------


class TestConfirmedView:
    @staticmethod
    def _job(uid, *, location="Austin, TX", **extra):
        job = {
            "uid": uid,
            "location": location,
            "location_verdict": "US",
            "age_hours": 1.0,
        }
        job.update(extra)

        return job

    def test_withholds_postings_still_queued_for_the_model(self):
        matches = [
            self._job("a", description="JD", analysis={"opt_eligible": "YES"}),
            self._job("b", description="JD"),
        ]

        published = _confirmed(matches, pending={"b"})

        assert [job["uid"] for job in published] == ["a"]
        # Withheld means untouched: no placeholder verdict is written that a
        # later pass would have to correct.
        assert "analysis" not in matches[1]

    def test_settled_postings_without_analysis_get_the_jd_fallback(self):
        matches = [self._job("a", description="JD text")]

        published = _confirmed(matches)

        assert published[0]["analysis"]["analysis_failed"] is True

    def test_drops_locations_that_are_not_confirmed_us(self):
        matches = [
            self._job("a"),
            self._job("b", location="Berlin", location_verdict="NON_US"),
        ]

        assert [job["uid"] for job in _confirmed(matches)] == ["a"]

    def test_orders_freshest_first(self):
        matches = [
            self._job("old", age_hours=40.0),
            self._job("new", age_hours=2.0),
        ]

        assert [job["uid"] for job in _confirmed(matches)] == ["new", "old"]

    def test_publishing_repeatedly_is_stable(self):
        """A partial publish must not change what the final one produces."""

        matches = [
            self._job("a", description="JD", analysis={"opt_eligible": "YES"}),
            self._job("b", description="JD"),
        ]

        partial = [job["uid"] for job in _confirmed(matches, pending={"b"})]
        final = [job["uid"] for job in _confirmed(matches)]

        assert partial == ["a"]
        assert final == ["a", "b"]


class TestIncrementalPublishing:
    """A scan must publish as it screens, not only when it finishes."""

    def test_results_are_saved_while_analysis_is_still_running(
        self,
        monkeypatch,
    ):
        import scanner.scan as scan_module

        jobs = [
            {
                "uid": f"greenhouse:acme:{index}",
                "company": "Acme",
                "title": "Software Engineer",
                "location": "Austin, TX",
                "description": "JD text",
                "age_hours": float(index),
                "categories": ["software"],
            }
            for index in range(4)
        ]

        saves: list[list[str]] = []

        monkeypatch.setattr(scan_module, "USE_OLLAMA_ANALYSIS", True)
        monkeypatch.setattr(scan_module, "PUBLISH_EVERY_SECONDS", 0.0)
        monkeypatch.setattr(
            scan_module,
            "load_companies",
            lambda dataset: [{"ats": "greenhouse", "slug": "acme"}],
        )
        monkeypatch.setattr(
            scan_module,
            "_scan_company",
            lambda company, lookback_hours, categories: jobs,
        )
        monkeypatch.setattr(scan_module, "load_analysis_cache", lambda: {})
        monkeypatch.setattr(
            scan_module,
            "save_analysis_cache",
            lambda cache: None,
        )
        monkeypatch.setattr(
            scan_module,
            "get_job_analysis",
            lambda job, cache: {"opt_eligible": "YES"},
        )
        monkeypatch.setattr(
            scan_module,
            "save_jobs",
            lambda saved, **kwargs: saves.append(
                [job["uid"] for job in saved]
            ),
        )
        monkeypatch.setattr(scan_module.status, "_persist", lambda: None)

        scan_module.run_scan(lookback_hours=24, dataset="core")

        # One save per screened posting, plus the final one — not a single
        # write at the end.
        assert len(saves) > 1
        # Each publish is a superset of the last: the list only ever grows.
        for earlier, later in zip(saves, saves[1:]):
            assert set(earlier).issubset(set(later))
        assert len(saves[0]) < len(saves[-1])
        assert len(saves[-1]) == len(jobs)

    def test_roles_are_listed_before_the_sweep_finishes(self, monkeypatch):
        """The whole point: no waiting for every board to be read."""

        import scanner.scan as scan_module

        boards = 12
        # Board reads block until released, so the sweep cannot possibly have
        # finished at the moment the first postings are published.
        gate = threading.Event()

        def board(company, lookback_hours, categories):
            index = company["index"]

            if index > 0:
                gate.wait(timeout=5)

            return [
                {
                    "uid": f"greenhouse:acme{index}:1",
                    "company": f"Acme {index}",
                    "title": "Software Engineer",
                    "location": "Austin, TX",
                    "description": "JD text",
                    "age_hours": 1.0,
                    "ats": "greenhouse",
                    "categories": ["software"],
                }
            ]

        observed: list[tuple[int, int]] = []

        def record(saved, **kwargs):
            observed.append(
                (scan_module.status.snapshot()["companies_done"], len(saved))
            )

            # Let the remaining boards go once something has been published.
            gate.set()

        monkeypatch.setattr(scan_module, "USE_OLLAMA_ANALYSIS", True)
        monkeypatch.setattr(scan_module, "PUBLISH_EVERY_SECONDS", 0.0)
        monkeypatch.setattr(
            scan_module,
            "load_companies",
            lambda dataset: [{"index": i} for i in range(boards)],
        )
        monkeypatch.setattr(scan_module, "_scan_company", board)
        monkeypatch.setattr(scan_module, "load_analysis_cache", lambda: {})
        monkeypatch.setattr(
            scan_module,
            "save_analysis_cache",
            lambda cache: None,
        )
        monkeypatch.setattr(
            scan_module,
            "get_job_analysis",
            lambda job, cache: {"opt_eligible": "YES"},
        )
        monkeypatch.setattr(scan_module, "save_jobs", record)
        monkeypatch.setattr(scan_module.status, "_persist", lambda: None)

        scan_module.run_scan(lookback_hours=24, dataset="core")

        assert observed, "nothing was ever published"

        first_done, first_count = observed[0]

        assert first_count >= 1
        assert first_done < boards, (
            "the first roles were only published after every board was read"
        )
        assert observed[-1][1] == boards


# --- Company logos ---------------------------------------------------------


class TestCompanyLogos:
    def test_logo_dev_url_uses_only_the_publishable_key(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            logos,
            "LOGO_DEV_PUBLISHABLE_KEY",
            "public-test-token",
        )

        url = logos.logo_dev_url(company_name="AT&T")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        assert parsed.netloc == "img.logo.dev"
        assert parsed.path == "/name/AT%26T"
        assert query["token"] == ["public-test-token"]
        assert "fallback" in query

    def test_cached_brandfetch_logo_gets_logo_dev_fallback(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            logos,
            "LOGO_DEV_PUBLISHABLE_KEY",
            "public-test-token",
        )
        monkeypatch.setattr(
            logos,
            "load_logo_cache",
            lambda: {
                "acme": {
                    "logo_url": "https://cdn.brandfetch.io/acme/icon",
                    "domain": "acme.com",
                }
            },
        )
        monkeypatch.setattr(
            logos,
            "_schedule_resolution",
            lambda _missing: None,
        )
        jobs = [{"company": "Acme"}]

        logos.prepare_job_logos(jobs)

        assert jobs[0]["logo_url"].startswith(
            "https://cdn.brandfetch.io/"
        )
        assert jobs[0]["logo_fallback_url"].startswith(
            "https://img.logo.dev/acme.com"
        )

    def test_logo_dev_search_resolves_when_brandfetch_does_not(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            logos,
            "_brandfetch_result",
            lambda _company: {},
        )
        monkeypatch.setattr(
            logos,
            "_logo_dev_result",
            lambda _company: {
                "logo_url": None,
                "domain": "acme.com",
                "provider": "logo.dev",
            },
        )

        resolved = logos.resolve_company_logo("Acme")

        assert resolved["domain"] == "acme.com"
        assert resolved["provider"] == "logo.dev"

    def test_domain_affinity_beats_a_loose_exact_name_match(self):
        results = [
            {"name": "Everpure", "domain": "purestorage.com"},
            {"name": "Pentair", "domain": "everpure.com"},
        ]

        selected = logos._best_result("Everpure", results)

        assert selected["domain"] == "everpure.com"


# --- ATS extraction --------------------------------------------------------


class TestAtsExtraction:
    def test_avature_reads_req_date_and_late_description(
        self,
        monkeypatch,
    ):
        search = """
        <article class="article article--result">
          <h3><a href="https://jobs.example.com/en_US/careers/JobDetail/
          Software-Engineer/80265">Software Engineer</a></h3>
          <span class="paragraph">Engineering</span>
          <div class="article__header__text__subtitle">
            <span>Austin, Texas, United States</span><br>
            <span>Req #: WD00102092</span><br>
            <span>Posted 07-Aug-2026</span>
          </div>
        </article>
        """
        detail = """
        <article class="article article--details">
          <h3>Description and Requirements</h3>
          <div class="article__content">
            <div class="article__content__view__field__value">
              <p>Build reliable APIs.</p><p>1+ years of experience.</p>
            </div>
          </div>
        </article>
        """
        monkeypatch.setattr(
            avature,
            "fetch_text",
            lambda url, **_kwargs: search if url.endswith("SearchJobs") else detail,
        )

        record = avature.fetch(
            {
                "name": "Lenovo",
                "slug": "https://jobs.example.com/en_US/careers",
            }
        )[0]

        assert record["job_id"] == "WD00102092"
        assert record["posted_at"].startswith("2026-08-07")
        assert record["location"] == "Austin, Texas, United States"
        assert record["team"] == "Engineering"
        assert avature.fetch_detail(record) == (
            "Build reliable APIs.\n1+ years of experience."
        )

    def test_oracle_reads_site_jobs_and_structured_detail(
        self,
        monkeypatch,
    ):
        site = (
            "https://example.fa.oraclecloud.com/hcmUI/"
            "CandidateExperience/en/sites/CX_1001"
        )
        monkeypatch.setattr(
            oracle,
            "_site_config",
            lambda _value: (site, "https://example.fa.oraclecloud.com", "CX_1001"),
        )

        def payload(url, **_kwargs):
            if url.endswith("recruitingCEJobRequisitionDetails"):
                return {
                    "items": [
                        {
                            "ExternalQualificationsStr": (
                                "<p>1+ years of experience.</p>"
                            ),
                            "ExternalResponsibilitiesStr": "<p>Build APIs.</p>",
                            "ExternalDescriptionStr": "<p>Join the team.</p>",
                        }
                    ]
                }

            return {
                "items": [
                    {
                        "Limit": 1,
                        "TotalJobsCount": 1,
                        "requisitionList": [
                            {
                                "Id": "R-1",
                                "Title": "Software Engineer",
                                "PostedDate": "2026-08-08",
                                "PrimaryLocation": "Austin, TX, United States",
                                "JobFunction": "Technology",
                                "secondaryLocations": [
                                    {"LocationName": "New York, NY, United States"}
                                ],
                                "requisitionFlexFields": [
                                    {
                                        "Prompt": "Compensation Range",
                                        "Value": "USD 100000 - USD 130000",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }

        monkeypatch.setattr(oracle, "fetch_json", payload)
        record = oracle.fetch({"name": "Acme", "slug": site})[0]

        assert record["url"] == f"{site}/job/R-1"
        assert record["location"] == (
            "Austin, TX, United States · New York, NY, United States"
        )
        assert record["team"] == "Technology"
        assert "USD 100000" in record["salary_context"]
        assert oracle.fetch_detail(record).startswith(
            "Qualifications\n1+ years of experience."
        )

    def test_jibe_extracts_complete_posting_without_duplicate_sections(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            jibe,
            "fetch_json",
            lambda *_args, **_kwargs: {
                "totalCount": 1,
                "jobs": [
                    {
                        "data": {
                            "req_id": "R-1",
                            "title": "Software Engineer",
                            "full_location": "Austin, Texas",
                            "categories": [{"name": "Engineering"}],
                            "posted_date": "2026-08-08 08:10 AM",
                            "description": "<p>Complete posting.</p>",
                            "responsibilities": "<p>Duplicate excerpt.</p>",
                            "tags1": ["USD $100,000/Yr."],
                            "meta_data": {
                                "canonical_url": (
                                    "https://careers.example.com/jobs/R-1"
                                )
                            },
                        }
                    }
                ],
            },
        )

        record = jibe.fetch(
            {"name": "AMD", "slug": "https://careers.example.com"}
        )[0]

        assert record["description"] == "Complete posting."
        assert record["salary_context"] == "USD $100,000/Yr."
        assert record["team"] == "Engineering"

    def test_atlassian_reads_its_consolidated_regional_feed(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            atlassian,
            "fetch_json",
            lambda *_args, **_kwargs: [
                {
                    "id": "25583",
                    "title": "Data Engineer",
                    "locations": ["Remote - US", "Austin, TX"],
                    "category": "Engineering",
                    "overview": "<p>Build data products.</p>",
                    "portalJobPost": {
                        "updatedDate": "2026-08-08 08:10 AM",
                        "portalUrl": (
                            "https://careers.example.com/jobs/25583/job"
                        ),
                    },
                }
            ],
        )

        record = atlassian.fetch(
            {"name": "Atlassian", "slug": "atlassian"}
        )[0]

        assert record["location"] == "Remote - US · Austin, TX"
        assert record["description"] == "Build data products."
        assert record["team"] == "Engineering"

    def test_icims_reads_and_paginates_public_job_cards(self, monkeypatch):
        pages = {
            0: """
                <ul class="iCIMS_JobsTable">
                  <li class="iCIMS_JobCardItem">
                    <div class="header left"><span class="field-label">Location</span><span>US-CA-San Francisco</span></div>
                    <a href="https://careers-acme.icims.com/jobs/101/software-engineer/job?in_iframe=1"><h3>Software Engineer</h3></a>
                    <div class="description">Build reliable systems.</div>
                    <dl class="iCIMS_JobHeaderGroup"><div class="iCIMS_JobHeaderTag"><dt class="iCIMS_JobHeaderField">Category:</dt><dd class="iCIMS_JobHeaderData">Engineering</dd></div></dl>
                  </li>
                </ul>
                <div class="iCIMS_Paging"><a href="https://careers-acme.icims.com/jobs/search?pr=1&amp;in_iframe=1">2</a></div>
            """,
            1: """
                <ul class="iCIMS_JobsTable">
                  <li class="iCIMS_JobCardItem">
                    <div class="header left"><span class="field-label">Location</span><span>US-NY-New York</span></div>
                    <a href="/jobs/102/data-engineer/job"><h3>Data Engineer</h3></a>
                  </li>
                </ul>
            """,
        }

        def page(url, **_kwargs):
            return pages[1 if "pr=1" in url else 0]

        monkeypatch.setattr(icims, "fetch_text", page)
        records = icims.fetch(
            {"name": "Acme", "slug": "careers-acme.icims.com"}
        )

        assert [record["job_id"] for record in records] == ["101", "102"]
        assert records[0]["location"] == "US-CA-San Francisco"
        assert records[0]["team"] == "Engineering"
        assert records[1]["url"] == (
            "https://careers-acme.icims.com/jobs/102/data-engineer/job"
        )

    def test_icims_hydrates_json_ld_job_details(self, monkeypatch):
        monkeypatch.setattr(
            icims,
            "fetch_text",
            lambda *_args, **_kwargs: """
                <script type="application/ld+json">
                {
                  "@context": "https://schema.org",
                  "@type": "JobPosting",
                  "title": "Data Engineer",
                  "datePosted": "2026-08-08T08:10:00Z",
                  "url": "https://careers-acme.icims.com/jobs/102/data-engineer/job",
                  "description": "<p>Build data products.</p>",
                  "occupationalCategory": "Engineering",
                  "jobLocation": {"address": {"addressLocality": "Austin", "addressRegion": "TX", "addressCountry": "US"}},
                  "baseSalary": {"currency": "USD", "value": {"minValue": 90000, "maxValue": 120000}}
                }
                </script>
            """,
        )
        hydrated = icims.hydrate(
            {
                "company": "Acme",
                "company_slug": "careers-acme.icims.com",
                "job_id": "102",
                "title": "Data Engineer",
                "url": "https://careers-acme.icims.com/jobs/102/data-engineer/job",
                "location": "",
                "team": "",
            }
        )

        assert hydrated["posted_at"] == "2026-08-08T08:10:00+00:00"
        assert hydrated["location"] == "Austin, TX, US"
        assert hydrated["description"] == "Build data products."
        assert '"currency": "USD"' in hydrated["salary_context"]

    def test_ibm_reads_scoped_search_attributes(self, monkeypatch):
        monkeypatch.setattr(
            ibm,
            "fetch_json",
            lambda *_args, **_kwargs: {
                "resultset": {
                    "searchresults": {
                        "totalresults": 1,
                        "searchresultlist": [
                            {
                                "title": "Data Engineer",
                                "url": (
                                    "https://careers.ibm.com/careers/"
                                    "JobDetail?jobId=124620"
                                ),
                                "docattributes": [
                                    {"field_text_01": "124620"},
                                    {"field_keyword_19": "Austin, US"},
                                    {"field_keyword_08": "Engineering"},
                                    {"dcdate": "2026-08-08"},
                                    {
                                        "raw_body": (
                                            "<p>Build reliable pipelines.</p>"
                                        )
                                    },
                                ],
                            }
                        ],
                    }
                }
            },
        )

        record = ibm.fetch({"name": "IBM", "slug": "ibm"})[0]

        assert record["job_id"] == "124620"
        assert record["location"] == "Austin, US"
        assert record["description"] == "Build reliable pipelines."

    def test_apple_uses_search_summary_and_current_us_filter(
        self,
        monkeypatch,
    ):
        posted = datetime.now(timezone.utc).isoformat()
        monkeypatch.setattr(apple, "_token", lambda: "csrf")
        monkeypatch.setattr(
            apple,
            "_page",
            lambda _token, _page: {
                "totalRecords": 1,
                "searchResults": [
                    {
                        "id": "2001",
                        "postingTitle": "Software Engineer",
                        "transformedPostingTitle": "software-engineer",
                        "postDateInGMT": posted,
                        "jobSummary": "Build Apple services.",
                        "locations": [
                            {"name": "Cupertino, California, United States"}
                        ],
                        "team": {
                            "teamCode": "SFTWR",
                            "teamName": "Software and Services",
                        },
                    }
                ],
            },
        )

        record = apple.fetch({"name": "Apple", "slug": "apple"})[0]

        assert record["location"].startswith("Cupertino")
        assert record["team"] == "Software and Services"
        assert record["url"].endswith("?team=SFTWR")

    def test_successfactors_hydrates_date_and_description(
        self,
        monkeypatch,
    ):
        search = """
        <p>Results 1 – 1 of <b>1</b></p>
        <table><tr class="data-row">
          <td><a class="jobTitle-link" href="/job/Austin-Engineer/123/">
            Software Engineer
          </a></td>
          <td><span class="jobLocation"><span>Austin, US</span></span></td>
        </tr></table>
        """
        detail = """
        <meta itemprop="datePosted" content="Sat Aug 08 08:10:00 UTC 2026">
        <span itemprop="description"><p>Build APIs.<br>Ship safely.</p></span>
        """

        monkeypatch.setattr(
            successfactors,
            "fetch_text",
            lambda url, **_kwargs: detail if "/123/" in url else search,
        )

        summary = successfactors.fetch(
            {"name": "SAP", "slug": "https://jobs.sap.com"}
        )[0]
        record = successfactors.hydrate(summary)

        assert record is not None
        assert record["posted_at"].startswith("2026-08-08T08:10:00")
        assert record["location"] == "Austin, US"
        assert record["description"] == "Build APIs.\nShip safely."

    def test_rippling_hydrates_only_after_title_match(self, monkeypatch):
        import scanner.scan as scan_module

        summaries = [
            {
                "ats": "rippling",
                "company": "Acme",
                "company_slug": "acme",
                "job_id": "sales-1",
                "title": "Account Executive",
                "posted_at": None,
            },
            {
                "ats": "rippling",
                "company": "Acme",
                "company_slug": "acme",
                "job_id": "software-1",
                "title": "Software Engineer",
                "posted_at": None,
            },
        ]
        hydrated = []

        def hydrate(job):
            hydrated.append(job["job_id"])

            return {
                **job,
                "posted_at": datetime.now(timezone.utc).isoformat(),
                "description": "Build APIs.",
            }

        monkeypatch.setattr(
            scan_module,
            "fetch_company",
            lambda _company: summaries,
        )
        monkeypatch.setattr(scan_module, "hydrate_job", hydrate)

        jobs = scan_module._scan_company(
            {"name": "Acme", "ats": "rippling", "slug": "acme"},
            24,
            ["software"],
        )

        assert hydrated == ["software-1"]
        assert [job["job_id"] for job in jobs] == ["software-1"]

    def test_ashby_falls_back_to_public_html_when_api_is_disabled(
        self,
        monkeypatch,
    ):
        def api_disabled(*_args, **_kwargs):
            raise ashby.BoardUnavailable("disabled")

        board = {
            "jobBoard": {
                "jobPostings": [
                    {
                        "id": "job-1",
                        "title": "Software Engineer",
                    }
                ]
            }
        }
        detail = {
            "posting": {
                "id": "job-1",
                "title": "Software Engineer",
                "locationName": "New York, NY",
                "secondaryLocationNames": ["Austin, TX"],
                "workplaceType": "Hybrid",
                "teamNames": ["Engineering", "Platform"],
                "descriptionHtml": "<p>Build reliable APIs.</p>",
                "compensationTierSummary": "$120K – $150K",
                "isListed": True,
            }
        }

        def html(url, **_kwargs):
            payload = detail if url.endswith("/job-1") else board
            date = '<script>{"datePosted":"2026-08-08"}</script>'

            return f"window.__appData = {json.dumps(payload)};{date}"

        monkeypatch.setattr(ashby, "fetch_json", api_disabled)
        monkeypatch.setattr(ashby, "fetch_text", html)

        record = ashby.fetch(
            {
                "name": "Acme",
                "slug": "acme",
                "source_url": "https://jobs.ashbyhq.com/acme/",
            }
        )[0]

        assert record["posted_at"].startswith("2026-08-08")
        assert record["location"] == "New York, NY · Austin, TX"
        assert record["team"] == "Engineering · Platform"
        assert record["description"] == "Build reliable APIs."
        assert record["salary_context"] == "$120K – $150K"

    def test_rippling_uses_detail_for_date_and_description(
        self,
        monkeypatch,
    ):
        def payload(url, **_kwargs):
            if url.endswith("/jobs"):
                return {
                    "items": [
                        {
                            "id": "job-1",
                            "name": "Data Analyst",
                            "url": "https://ats.rippling.com/acme/jobs/job-1",
                            "locations": [
                                {
                                    "name": "Remote - US",
                                    "workplaceType": "REMOTE",
                                }
                            ],
                        }
                    ],
                    "totalPages": 1,
                }

            return {
                "uuid": "job-1",
                "name": "Data Analyst",
                "url": "https://ats.rippling.com/acme/jobs/job-1",
                "createdOn": "2026-08-08T10:00:00-07:00",
                "description": {
                    "company": "<p>About Acme.</p>",
                    "role": "<p>Analyze product data.</p>",
                },
                "department": {"name": "Analytics"},
                "payRangeDetails": [{"min": 100000, "max": 130000}],
                "unlistedFromSearch": False,
            }

        monkeypatch.setattr(rippling, "fetch_json", payload)

        summary = rippling.fetch(
            {"name": "Acme", "slug": "acme"}
        )[0]
        record = rippling.hydrate(summary)

        assert summary["posted_at"] is None
        assert summary["description"] == ""
        assert record is not None
        assert record["posted_at"].startswith("2026-08-08T17:00:00")
        assert record["location"] == "Remote - US"
        assert record["team"] == "Analytics"
        assert record["description"] == (
            "About Acme.\n\nAnalyze product data."
        )
        assert '"min": 100000' in record["salary_context"]

    def test_greenhouse_prefers_first_published_over_edit_time(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            greenhouse,
            "fetch_json",
            lambda *_args, **_kwargs: {
                "jobs": [
                    {
                        "id": 1,
                        "title": "Software Engineer",
                        "absolute_url": "https://example.com/job",
                        "first_published": "2026-07-01T12:00:00Z",
                        "created_at": "2026-07-01T11:00:00Z",
                        "updated_at": "2026-07-28T12:00:00Z",
                        "content": "<p>3+ years of experience.</p>",
                    }
                ]
            },
        )

        record = greenhouse.fetch(
            {"name": "Acme", "slug": "acme"}
        )[0]

        assert record["posted_at"].startswith("2026-07-01T12:00:00")
        assert record["description"] == "3+ years of experience."

    def test_smartrecruiters_keeps_requirements_before_boilerplate(
        self,
        monkeypatch,
    ):
        payload = {
            "jobAd": {
                "sections": {
                    "companyDescription": {
                        "title": "About us",
                        "text": "<p>" + ("Company story " * 1_000) + "</p>",
                    },
                    "jobDescription": {
                        "title": "The role",
                        "text": "<p>Build APIs.</p>",
                    },
                    "qualifications": {
                        "title": "Qualifications",
                        "text": "<p>Required: 4+ years of experience.</p>",
                    },
                }
            }
        }
        # Exercise the helper through the same payload shape returned by the
        # detail endpoint, without a live network call.
        monkeypatch.setattr(
            smartrecruiters,
            "fetch_json",
            lambda *_args, **_kwargs: payload,
        )
        text = smartrecruiters.fetch_detail(
            {
                "company_slug": "acme",
                "job_id": "1",
            }
        )

        assert text.index("Qualifications") < text.index("About us")
        assert "4+ years of experience" in text[:8_000]

    def test_lever_paginates_and_keeps_all_locations(
        self,
        monkeypatch,
    ):
        calls = []

        def fake_fetch(_url, *, params):
            calls.append(params["skip"])

            if params["skip"] == 0:
                return [
                    {
                        "id": str(index),
                        "text": "Software Engineer",
                        "categories": {"location": "Austin, TX"},
                    }
                    for index in range(100)
                ]

            return [
                {
                    "id": "last",
                    "text": "Software Engineer",
                    "categories": {
                        "allLocations": ["Austin, TX", "Remote — US"],
                    },
                }
            ]

        monkeypatch.setattr(lever, "fetch_json", fake_fetch)

        records = lever.fetch({"name": "Acme", "slug": "acme"})

        assert calls == [0, 100]
        assert len(records) == 101
        assert records[-1]["location"] == "Austin, TX · Remote — US"

    def test_workday_stops_when_a_tenant_repeats_the_same_page(
        self,
        monkeypatch,
    ):
        calls = []
        repeated = [
            {
                "title": f"Software Engineer {index}",
                "externalPath": f"/job/{index}",
                "bulletFields": [f"R-{index}"],
                "postedOn": "Posted Today",
            }
            for index in range(workday.PAGE_LIMIT)
        ]

        def fake_fetch(*_args, **kwargs):
            calls.append(kwargs["json_body"]["offset"])
            return {"jobPostings": repeated}

        monkeypatch.setattr(workday, "fetch_json", fake_fetch)

        records = workday.fetch(
            {
                "name": "Acme",
                "slug": "https://acme.wd5.myworkdayjobs.com/Jobs",
            }
        )

        assert calls == [0, workday.PAGE_LIMIT]
        assert len(records) == workday.PAGE_LIMIT

    def test_workday_apply_url_keeps_the_board_segment(self, monkeypatch):
        """
        `externalPath` is relative to the board, not the host. Hung off the
        bare origin every apply link 404s, which is exactly what shipped.
        """

        def fake_fetch(*_args, **_kwargs):
            return {
                "jobPostings": [
                    {
                        "title": "Data Analyst",
                        "externalPath": "/job/Austin-TX/Data-Analyst_JR113528",
                        "bulletFields": ["JR113528"],
                        "postedOn": "Posted Today",
                    }
                ]
            }

        monkeypatch.setattr(workday, "fetch_json", fake_fetch)

        records = workday.fetch(
            {
                "name": "Acrisure",
                "slug": "https://acrisure.wd1.myworkdayjobs.com/acrisure",
            }
        )

        assert records[0]["url"] == (
            "https://acrisure.wd1.myworkdayjobs.com"
            "/acrisure/job/Austin-TX/Data-Analyst_JR113528"
        )

    def test_workday_detail_path_survives_the_public_url_round_trip(self):
        """
        `fetch_detail` rebuilds the CXS path from the stored URL, so the board
        segment has to come back off — including for URLs stored before the
        fix, and for boards that carry a locale prefix.
        """

        assert workday.external_path(
            "/acrisure/job/Austin-TX/Data-Analyst_JR1",
            "acrisure",
        ) == "/job/Austin-TX/Data-Analyst_JR1"

        assert workday.external_path(
            "/en-US/acrisure/job/Austin-TX/Data-Analyst_JR1",
            "acrisure",
        ) == "/job/Austin-TX/Data-Analyst_JR1"

        # Stored before the board segment was added.
        assert workday.external_path(
            "/job/Austin-TX/Data-Analyst_JR1",
            "acrisure",
        ) == "/job/Austin-TX/Data-Analyst_JR1"
