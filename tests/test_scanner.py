"""
Backend tests.

Focused on the logic that decides what the product returns — the boolean
search, the time window, and US screening. Network adapters are covered by
shape tests, not live calls.

    python3 -m pytest tests/ -q
"""

from __future__ import annotations

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
from scanner.ats import greenhouse, lever, smartrecruiters, workday
from scanner.companies import (
    dataset_for_ats,
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
    def test_supported_boards_route_to_their_catalog(self):
        for ats in (
            "greenhouse",
            "ashby",
            "lever",
            "smartrecruiters",
            "workable",
        ):
            assert dataset_for_ats(ats) == "main"

        assert dataset_for_ats("workday") == "workday"

    def test_unadapted_boards_route_to_plus(self):
        # The point of "plus": a board nothing can read is parked, not lost.
        for ats in ("taleo", "icims", "", None):
            assert dataset_for_ats(ats) == "plus"

    def test_routing_ignores_case_and_padding(self):
        assert dataset_for_ats("  Greenhouse ") == "main"
        assert dataset_for_ats("WORKDAY") == "workday"

    def test_unknown_dataset_falls_back_to_main(self):
        assert resolve_dataset("nope") == "main"
        assert resolve_dataset(None) == "main"
        assert resolve_dataset("plus") == "plus"

    def test_scannable_catalogs_hold_only_their_own_boards(self):
        for dataset in ("main", "workday"):
            for company in load_companies(dataset):
                assert dataset_for_ats(company["ats"]) == dataset

    def test_plus_never_shadows_a_scannable_row(self):
        # "plus" holds unscannable rows — a board with no adapter, or one
        # that named an adapter but did not answer — plus a handful of
        # hand-verified extras not yet folded into "main". None of it may
        # also sit in a scannable catalog, or one company would be scanned
        # under a slug already known to be dead (or double-counted).
        scannable = {
            (company["ats"], company["slug"].casefold())
            for dataset in ("main", "workday")
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

        scan_module.run_scan(lookback_hours=24, dataset="main")

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

        scan_module.run_scan(lookback_hours=24, dataset="main")

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
