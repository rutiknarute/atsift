from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

import app


class AtsAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.future = datetime.now(timezone.utc) + timedelta(hours=1)
        brandfetch_key_patcher = patch.object(
            app,
            "BRANDFETCH_SECRET_API_KEY",
            "",
        )
        brandfetch_key_patcher.start()
        self.addCleanup(brandfetch_key_patcher.stop)

    def test_company_catalog_has_all_supported_ats(self) -> None:
        companies = app.load_companies(app.COMPANIES_PATH)

        self.assertEqual(16_401, len(companies))
        self.assertEqual(
            {
                "greenhouse": 4_960,
                "ashby": 2_856,
                "lever": 2_112,
                "smartrecruiters": 2_208,
                "workable": 4_265,
                "workday": 0,
            },
            app.company_counts_by_ats(companies),
        )

    def test_focused_company_catalog_is_balanced(self) -> None:
        companies = app.load_companies(
            app.COMPANY_DATASET_PATHS["focused_2500"]
        )

        self.assertEqual(2_500, len(companies))
        self.assertEqual(
            {
                "greenhouse": 500,
                "ashby": 500,
                "lever": 500,
                "smartrecruiters": 500,
                "workable": 500,
                "workday": 0,
            },
            app.company_counts_by_ats(companies),
        )

    def test_verified_us_company_catalog_has_supported_ats(self) -> None:
        companies = app.load_companies(
            app.COMPANY_DATASET_PATHS["verified_us"]
        )

        self.assertEqual(8_011, len(companies))
        self.assertEqual(
            {
                "greenhouse": 3_648,
                "ashby": 2_317,
                "lever": 1_326,
                "smartrecruiters": 600,
                "workable": 120,
                "workday": 0,
            },
            app.company_counts_by_ats(companies),
        )

    def test_seed_company_catalog_has_supported_ats(self) -> None:
        companies = app.load_companies(
            app.COMPANY_DATASET_PATHS["seed_data"]
        )

        self.assertEqual(1_952, len(companies))
        self.assertEqual(
            {
                "greenhouse": 837,
                "ashby": 488,
                "lever": 349,
                "smartrecruiters": 173,
                "workable": 71,
                "workday": 34,
            },
            app.company_counts_by_ats(companies),
        )

        keys = {
            (company["ats"], company["slug"].casefold())
            for company in companies
        }
        self.assertEqual(len(companies), len(keys))

    def test_company_dataset_catalogs_include_all_options(self) -> None:
        catalogs = app.company_dataset_catalogs()
        self.assertEqual(
            ["full", "focused_2500", "verified_us", "seed_data"],
            [catalog["id"] for catalog in catalogs],
        )

    def test_visible_jobs_are_filtered_by_company_dataset(self) -> None:
        jobs = [
            {
                "uid": "ashby:1mind:job-1",
                "source": "ashby",
                "slug": "1mind",
                "title": "Software Engineer I",
                "location": "United States",
                "first_published_at": self.future.isoformat(),
            },
            {
                "uid": "ashby:0g:job-2",
                "source": "ashby",
                "slug": "0g",
                "title": "Software Engineer I",
                "location": "United States",
                "first_published_at": self.future.isoformat(),
            },
        ]

        with TemporaryDirectory() as temporary_directory:
            jobs_store_path = (
                Path(temporary_directory)
                / "jobs_store.json"
            )
            app.save_json_atomic(jobs_store_path, jobs)

            with patch.object(
                app,
                "JOBS_STORE_PATH",
                jobs_store_path,
            ):
                full_jobs = app.load_visible_jobs(72, "full")
                focused_jobs = app.load_visible_jobs(
                    72,
                    "focused_2500",
                )

        self.assertEqual(2, len(full_jobs))
        self.assertEqual(
            ["ashby:1mind:job-1"],
            [job["uid"] for job in focused_jobs],
        )

    def test_visible_jobs_deduplicate_case_variant_slugs(self) -> None:
        jobs = [
            {
                "uid": "ashby:1MIND:job-1",
                "source": "ashby",
                "slug": "1MIND",
                "id": "job-1",
                "title": "Software Engineer I",
                "location": "United States",
                "first_published_at": self.future.isoformat(),
                "last_seen_at": "2026-07-20T12:00:00+00:00",
            },
            {
                "uid": "ashby:1mind:job-1",
                "source": "ashby",
                "slug": "1mind",
                "id": "job-1",
                "title": "Software Engineer I",
                "location": "United States",
                "first_published_at": self.future.isoformat(),
                "last_seen_at": "2026-07-20T13:00:00+00:00",
            },
        ]

        with TemporaryDirectory() as temporary_directory:
            jobs_store_path = (
                Path(temporary_directory)
                / "jobs_store.json"
            )
            app.save_json_atomic(jobs_store_path, jobs)

            with patch.object(
                app,
                "JOBS_STORE_PATH",
                jobs_store_path,
            ):
                visible_jobs = app.load_visible_jobs(72, "full")

        self.assertEqual(1, len(visible_jobs))
        self.assertEqual(
            "ashby:1mind:job-1",
            visible_jobs[0]["uid"],
        )

    def test_title_categories_cover_all_requested_role_groups(self) -> None:
        cases = {
            "Software Engineer I": {"software"},
            "Entry-Level Graduate Program": {"new_grad"},
            "Business Intelligence Analyst": {"data_analyst"},
            "Analytics Engineer": {"data_engineer"},
            "Generative AI Engineer": {"ai_ml"},
            "GTM Automation Engineer": {"gtm"},
            "New Grad Software Engineer": {
                "software",
                "new_grad",
            },
            "AI Data Analyst": {
                "data_analyst",
                "ai_ml",
            },
        }

        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(
                    expected,
                    set(app.title_categories(title)),
                )
                self.assertTrue(
                    app.title_matches_keywords(title)
                )

    def test_title_categories_apply_category_specific_exclusions(self) -> None:
        for title in (
            "Senior Data Engineer",
            "Principal Growth Engineer",
            "GTM Recruiter",
        ):
            with self.subTest(title=title):
                self.assertEqual([], app.title_categories(title))
                self.assertFalse(
                    app.title_matches_keywords(title)
                )

        self.assertEqual(
            ["gtm"],
            app.title_categories("AI Solutions Architect"),
        )

    def test_keyword_boundaries_protect_short_terms(self) -> None:
        self.assertEqual([], app.title_categories("SRE I"))
        self.assertEqual([], app.title_categories("Build Engineer"))

    def test_ui_preparation_backfills_role_categories(self) -> None:
        prepared = app.prepare_jobs_for_ui(
            [
                {
                    "title": "AI Data Analyst",
                    "source": "ashby",
                }
            ]
        )

        self.assertEqual(
            ["data_analyst", "ai_ml"],
            prepared[0]["categories"],
        )

    def test_provider_error_classification_handles_expected_statuses(self) -> None:
        missing_response = Mock(status_code=404)
        missing_error = requests.HTTPError(response=missing_response)
        self.assertEqual(
            ("missing_resource", "Greenhouse board is unavailable"),
            app.classify_provider_error(missing_error, "greenhouse"),
        )

        rate_limited_response = Mock(status_code=429)
        rate_limited_error = requests.HTTPError(
            response=rate_limited_response
        )
        self.assertEqual(
            ("rate_limited", "Workable is rate limiting requests"),
            app.classify_provider_error(
                rate_limited_error,
                "workable",
            ),
        )

    def test_company_logo_url_uses_encoded_name_lookup(self) -> None:
        with patch.object(
            app,
            "LOGO_DEV_PUBLISHABLE_KEY",
            "pk_test",
        ):
            self.assertEqual(
                (
                    "https://img.logo.dev/name/AT%26T"
                    "?token=pk_test"
                    "&size=48&retina=true&format=webp"
                ),
                app.company_logo_url("AT&T"),
            )

    def test_ui_preparation_prefers_cached_brandfetch_logo(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            cache_path = (
                Path(temporary_directory)
                / "brandfetch_logo_cache.json"
            )
            cache_path.write_text(
                json.dumps(
                    {
                        "acme": {
                            "logo_url": (
                                "https://cdn.brandfetch.io/acme/icon"
                            ),
                            "domain": "acme.com",
                        }
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                app,
                "BRANDFETCH_LOGO_CACHE_PATH",
                cache_path,
            ):
                prepared = app.prepare_jobs_for_ui(
                    [
                        {
                            "company": "Acme",
                            "title": "Software Engineer",
                            "source": "ashby",
                        }
                    ]
                )

        self.assertEqual(
            "https://cdn.brandfetch.io/acme/icon",
            prepared[0]["logo_url"],
        )
        self.assertIsNotNone(
            prepared[0]["logo_fallback_url"],
        )

    def test_ui_preparation_schedules_missing_logos_without_waiting(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            cache_path = (
                Path(temporary_directory)
                / "brandfetch_logo_cache.json"
            )
            cache_path.write_text("{}", encoding="utf-8")

            with (
                patch.object(
                    app,
                    "BRANDFETCH_LOGO_CACHE_PATH",
                    cache_path,
                ),
                patch.object(
                    app,
                    "LOGO_DEV_PUBLISHABLE_KEY",
                    "pk_test",
                ),
                patch.object(
                    app,
                    "BRANDFETCH_SECRET_API_KEY",
                    "secret_test",
                ),
                patch.object(
                    app,
                    "schedule_brandfetch_logo_resolution",
                ) as schedule_resolution,
            ):
                prepared = app.prepare_jobs_for_ui(
                    [
                        {
                            "company": "Acme",
                            "title": "Software Engineer",
                            "source": "ashby",
                        }
                    ]
                )

        schedule_resolution.assert_called_once_with(["Acme"])
        self.assertEqual(
            (
                "https://img.logo.dev/name/Acme"
                "?token=pk_test"
                "&size=48&retina=true&format=webp"
            ),
            prepared[0]["logo_url"],
        )

    def test_company_catalog_cache_invalidates_when_csv_changes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            csv_path = Path(temporary_directory) / "companies.csv"
            csv_path.write_text(
                "name,ats,slug\nAcme,ashby,acme\n",
                encoding="utf-8",
            )

            first_catalog = app.load_companies(csv_path)

            csv_path.write_text(
                (
                    "name,ats,slug\n"
                    "Acme,ashby,acme\n"
                    "Example,lever,example\n"
                ),
                encoding="utf-8",
            )

            second_catalog = app.load_companies(csv_path)

        self.assertEqual(1, len(first_catalog))
        self.assertEqual(2, len(second_catalog))

    def test_viewed_job_api_persists_first_click_for_future_results(self) -> None:
        uid = "greenhouse:example:job-1"

        with TemporaryDirectory() as temporary_directory:
            viewed_jobs_path = (
                Path(temporary_directory)
                / "viewed_jobs.json"
            )

            with patch.object(
                app,
                "VIEWED_JOBS_PATH",
                viewed_jobs_path,
            ):
                client = app.app.test_client()
                first_response = client.post(
                    "/api/jobs/viewed",
                    json={"uid": uid},
                )
                second_response = client.post(
                    "/api/jobs/viewed",
                    json={"uid": uid},
                )

                self.assertEqual(
                    200,
                    first_response.status_code,
                )
                self.assertEqual(
                    first_response.json["viewed_at"],
                    second_response.json["viewed_at"],
                )

                prepared = app.prepare_jobs_for_ui(
                    [
                        {
                            "uid": uid,
                            "title": "Software Engineer I",
                            "source": "greenhouse",
                        }
                    ]
                )

                self.assertEqual(
                    first_response.json["viewed_at"],
                    prepared[0]["viewed_at"],
                )

    def test_viewed_job_lookup_matches_legacy_slug_casing(self) -> None:
        viewed_at = "2026-07-20T12:00:00+00:00"

        with TemporaryDirectory() as temporary_directory:
            viewed_jobs_path = (
                Path(temporary_directory)
                / "viewed_jobs.json"
            )
            viewed_jobs_path.write_text(
                json.dumps(
                    {
                        "smartrecruiters:Example:job-1": viewed_at,
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                app,
                "VIEWED_JOBS_PATH",
                viewed_jobs_path,
            ):
                prepared = app.prepare_jobs_for_ui(
                    [
                        {
                            "uid": "smartrecruiters:example:job-1",
                            "title": "Software Engineer I",
                            "source": "smartrecruiters",
                        }
                    ]
                )

        self.assertEqual(viewed_at, prepared[0]["viewed_at"])

    def test_mark_viewed_reuses_legacy_slug_casing_timestamp(self) -> None:
        viewed_at = "2026-07-20T12:00:00+00:00"

        with TemporaryDirectory() as temporary_directory:
            viewed_jobs_path = (
                Path(temporary_directory)
                / "viewed_jobs.json"
            )
            viewed_jobs_path.write_text(
                json.dumps(
                    {
                        "smartrecruiters:Example:job-1": viewed_at,
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                app,
                "VIEWED_JOBS_PATH",
                viewed_jobs_path,
            ):
                result = app.mark_job_viewed(
                    "smartrecruiters:example:job-1"
                )

        self.assertEqual(viewed_at, result)

    def test_viewed_job_api_rejects_invalid_uids(self) -> None:
        client = app.app.test_client()
        response = client.post(
            "/api/jobs/viewed",
            json={"uid": "unknown-job"},
        )

        self.assertEqual(400, response.status_code)

    def test_us_location_filter_handles_known_and_remote_locations(self) -> None:
        self.assertIs(
            True,
            app.us_location_decision("Boise, ID"),
        )
        self.assertIs(
            True,
            app.us_location_decision("United States"),
        )
        self.assertIs(
            True,
            app.us_location_decision("Remote"),
        )
        self.assertIs(
            True,
            app.us_location_decision(
                "",
                country="United States",
            ),
        )

    def test_us_location_filter_rejects_known_foreign_locations(self) -> None:
        self.assertIs(
            False,
            app.us_location_decision("Toronto, Ontario, Canada"),
        )
        self.assertIs(
            False,
            app.us_location_decision("Remote - Europe"),
        )
        self.assertIs(
            False,
            app.us_location_decision("Cambridge, UK"),
        )
        self.assertIs(
            False,
            app.us_location_decision("Dublin, IE"),
        )
        self.assertIs(
            False,
            app.us_location_decision(
                "Remote",
                country="Canada",
                is_remote=True,
            ),
        )

    def test_city_only_location_uses_analysis_decision(self) -> None:
        self.assertIsNone(
            app.us_location_decision("Austin")
        )
        self.assertTrue(
            app.stored_job_is_us_eligible(
                {
                    "location": "Austin",
                    "analysis": {
                        "us_location_eligible": "YES",
                    },
                }
            )
        )
        self.assertFalse(
            app.stored_job_is_us_eligible(
                {
                    "location": "London",
                    "analysis": {
                        "us_location_eligible": "NO",
                    },
                }
            )
        )

    def test_relative_time_keeps_minutes_under_24_hours(self) -> None:
        posted_at = (
            datetime.now(timezone.utc)
            - timedelta(hours=2, minutes=23, seconds=5)
        ).isoformat()

        self.assertEqual(
            "2 hours 23 minutes ago",
            app.relative_time(posted_at),
        )

    def test_short_lookback_options_are_available(self) -> None:
        self.assertEqual(
            (1, 2, 4, 6, 12, 24, 48, 72),
            app.ALLOWED_LOOKBACK_HOURS,
        )

        client = app.app.test_client()

        for hours in (1, 2, 4):
            response = client.get(
                f"/api/jobs?lookback_hours={hours}"
            )
            self.assertEqual(200, response.status_code)

        page = client.get("/")
        self.assertEqual(200, page.status_code)
        self.assertIn(b'roleCategoryFilter', page.data)

    def test_api_rejects_unknown_company_dataset(self) -> None:
        client = app.app.test_client()

        jobs_response = client.get(
            "/api/jobs?lookback_hours=48&dataset=unknown"
        )
        scan_response = client.post(
            "/api/scan",
            json={
                "lookback_hours": 48,
                "dataset": "unknown",
            },
        )

        self.assertEqual(400, jobs_response.status_code)
        self.assertEqual(400, scan_response.status_code)

    def test_lever_record_normalizes_public_posting(self) -> None:
        record = app.lever_job_record(
            {
                "id": "lever-1",
                "text": "Software Engineer I",
                "createdAt": int(self.future.timestamp() * 1000),
                "categories": {
                    "team": "Engineering",
                    "allLocations": ["San Francisco, CA", "Remote"],
                },
                "descriptionPlain": "Build reliable software.",
                "lists": [
                    {
                        "text": "Requirements",
                        "content": "<li>Python</li><li>React</li>",
                    }
                ],
                "hostedUrl": "https://jobs.lever.co/example/lever-1",
                "applyUrl": "https://jobs.lever.co/example/lever-1/apply",
            },
            "Example",
            "example",
            72,
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual("lever", record["source"])
        self.assertEqual("Engineering", record["team"])
        self.assertIn("Python", record["description"])
        self.assertIn("Remote", record["location"])

    def test_smartrecruiters_record_normalizes_details(self) -> None:
        record = app.smartrecruiters_job_record(
            {
                "id": "smart-1",
                "name": "Software Engineer I",
                "releasedDate": self.future.isoformat(),
                "active": True,
                "location": {
                    "fullLocation": "Austin, TX, United States",
                    "hybrid": True,
                },
                "department": {"label": "Software Engineering"},
                "postingUrl": "https://jobs.smartrecruiters.com/example/smart-1",
                "applyUrl": "https://jobs.smartrecruiters.com/example/smart-1/apply",
                "jobAd": {
                    "sections": {
                        "jobDescription": {
                            "title": "Job Description",
                            "text": "<p>Build APIs.</p>",
                        },
                        "qualifications": {
                            "title": "Qualifications",
                            "text": "<p>Python and SQL.</p>",
                        },
                    }
                },
            },
            "Example",
            "example",
            72,
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual("smartrecruiters", record["source"])
        self.assertEqual("Software Engineering", record["team"])
        self.assertIn("Hybrid", record["location"])
        self.assertIn("Python and SQL", record["description"])

    def test_workable_record_normalizes_public_job(self) -> None:
        record = app.workable_job_record(
            {
                "shortcode": "WORK-1",
                "title": "Software Engineer I",
                "published_on": self.future.date().isoformat(),
                "city": "Boston",
                "state": "Massachusetts",
                "country": "United States",
                "telecommuting": True,
                "department": "Engineering",
                "description": "<p>Build services with Go.</p>",
                "url": "https://apply.workable.com/j/WORK-1",
                "application_url": "https://apply.workable.com/j/WORK-1/apply",
            },
            "Example",
            "example",
            72,
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual("workable", record["source"])
        self.assertEqual("Engineering", record["team"])
        self.assertIn("Remote", record["location"])
        self.assertEqual("Build services with Go.", record["description"])

    def test_workday_site_config_parses_tenant_and_site(self) -> None:
        config = app.workday_site_config(
            "https://capitalone.wd12.myworkdayjobs.com/Capital_One"
        )

        self.assertEqual("capitalone", config["tenant"])
        self.assertEqual("Capital_One", config["site"])
        self.assertEqual(
            "https://capitalone.wd12.myworkdayjobs.com/"
            "wday/cxs/capitalone/Capital_One",
            config["cxs_url"],
        )

    def test_workday_posted_date_handles_relative_labels(self) -> None:
        reference = datetime(
            2026,
            7,
            20,
            12,
            tzinfo=timezone.utc,
        )

        self.assertEqual(
            "2026-07-20",
            app.workday_posted_date(
                "Posted Today",
                now=reference,
            ),
        )
        self.assertEqual(
            "2026-07-19",
            app.workday_posted_date(
                "Posted Yesterday",
                now=reference,
            ),
        )
        self.assertEqual(
            "2026-07-17",
            app.workday_posted_date(
                "Posted 3 Days Ago",
                now=reference,
            ),
        )

    def test_workday_record_normalizes_public_job(self) -> None:
        slug = (
            "https://example.wd5.myworkdayjobs.com/"
            "External_Careers"
        )
        record = app.workday_job_record(
            {
                "jobPostingInfo": {
                    "title": "Software Engineer I",
                    "startDate": self.future.date().isoformat(),
                    "jobReqId": "WD-100",
                    "location": "San Francisco, CA",
                    "jobRequisitionLocation": {
                        "country": {
                            "descriptor": "United States of America",
                            "alpha2Code": "US",
                        },
                    },
                    "externalUrl": (
                        f"{slug}/job/San-Francisco/"
                        "Software-Engineer-I_WD-100"
                    ),
                    "jobDescription": (
                        "<p>Build services with Python.</p>"
                    ),
                    "canApply": True,
                    "posted": True,
                },
                "hiringOrganization": {
                    "name": "Platform Engineering",
                },
            },
            {
                "title": "Software Engineer I",
                "externalPath": (
                    "/job/San-Francisco/"
                    "Software-Engineer-I_WD-100"
                ),
                "postedOn": "Posted Today",
                "bulletFields": ["WD-100"],
            },
            "Example",
            slug,
            72,
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual("workday", record["source"])
        self.assertEqual("WD-100", record["id"])
        self.assertEqual("Platform Engineering", record["team"])
        self.assertEqual(
            "Build services with Python.",
            record["description"],
        )

    def test_company_order_round_robins_ats_hosts(self) -> None:
        companies = [
            {"name": ats, "ats": ats, "slug": ats}
            for ats in app.SUPPORTED_ATS
        ]
        companies.extend(
            [
                {"name": "Second Greenhouse", "ats": "greenhouse", "slug": "greenhouse-2"},
                {"name": "Second Ashby", "ats": "ashby", "slug": "ashby-2"},
            ]
        )

        ordered = app.interleave_companies(companies)

        self.assertEqual(
            list(app.SUPPORTED_ATS),
            [
                company["ats"]
                for company in ordered[:len(app.SUPPORTED_ATS)]
            ],
        )


if __name__ == "__main__":
    unittest.main()
