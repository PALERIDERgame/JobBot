from __future__ import annotations

import json
import types
import unittest
from unittest.mock import MagicMock, patch

from config import JobBotConfig
from scrapers.jobspy_scraper import JobSpyScraper
from scrapers.scraper_router import ScraperRouter
from scrapers.usajobs_api import USAJobsScraper


class ScraperTests(unittest.TestCase):
    @patch("scrapers.usajobs_api.time.sleep")
    @patch("scrapers.usajobs_api.build_opener")
    def test_fetch_jobs_normalizes_response(self, build_opener_mock, _sleep_mock) -> None:
        payload = {
            "SearchResult": {
                "SearchResultItems": [
                    {
                        "MatchedObjectDescriptor": {
                            "OrganizationName": "Agency",
                            "PositionTitle": "Python Developer",
                            "PositionLocationDisplay": "Remote",
                            "PositionURI": "https://example.com/view",
                            "ApplyURI": ["https://example.com/apply"],
                            "PublicationStartDate": "2026-01-01T00:00:00+00:00",
                            "UserArea": {"Details": {"JobSummary": "Build systems"}},
                            "PositionRemuneration": [{"MinimumRange": "100000", "MaximumRange": "120000"}],
                        }
                    }
                ]
            }
        }
        response = MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        build_opener_mock.return_value = opener

        config = JobBotConfig()
        jobs = USAJobsScraper(config).fetch_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0][0].title, "Python Developer")

    @patch("scrapers.usajobs_api.time.sleep")
    @patch("scrapers.usajobs_api.build_opener")
    def test_fetch_jobs_detects_explicit_email_apply(self, build_opener_mock, _sleep_mock) -> None:
        payload = {
            "SearchResult": {
                "SearchResultItems": [
                    {
                        "MatchedObjectDescriptor": {
                            "OrganizationName": "Agency",
                            "PositionTitle": "Python Developer",
                            "PositionLocationDisplay": "Remote",
                            "PositionURI": "https://example.com/view",
                            "ApplyURI": ["https://example.com/apply"],
                            "PublicationStartDate": "2026-01-01T00:00:00+00:00",
                            "UserArea": {
                                "Details": {
                                    "HowToApply": "Please email your resume and cover letter to hiring@example.com."
                                }
                            },
                        }
                    }
                ]
            }
        }
        response = MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        build_opener_mock.return_value = opener

        jobs = USAJobsScraper(JobBotConfig()).fetch_jobs()
        self.assertEqual(jobs[0][0].apply_method, "email")
        self.assertEqual(jobs[0][0].hiring_manager_email, "hiring@example.com")

    @patch("scrapers.usajobs_api.time.sleep")
    @patch("scrapers.usajobs_api.build_opener")
    def test_fetch_jobs_ignores_incidental_email_without_apply_instruction(self, build_opener_mock, _sleep_mock) -> None:
        payload = {
            "SearchResult": {
                "SearchResultItems": [
                    {
                        "MatchedObjectDescriptor": {
                            "OrganizationName": "Agency",
                            "PositionTitle": "Python Developer",
                            "PositionLocationDisplay": "Remote",
                            "PositionURI": "https://example.com/view",
                            "ApplyURI": ["https://example.com/apply"],
                            "PublicationStartDate": "2026-01-01T00:00:00+00:00",
                            "UserArea": {
                                "Details": {
                                    "JobSummary": "For accommodation questions, contact hr@example.com."
                                }
                            },
                        }
                    }
                ]
            }
        }
        response = MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        build_opener_mock.return_value = opener

        jobs = USAJobsScraper(JobBotConfig()).fetch_jobs()
        self.assertEqual(jobs[0][0].apply_method, "board")
        self.assertEqual(jobs[0][0].hiring_manager_email, "")

    def test_jobspy_normalizes_response(self) -> None:
        fake_module = types.SimpleNamespace(scrape_jobs=lambda **_kwargs: [{"unused": True}])
        config = JobBotConfig()
        config.source.provider = "jobspy"
        config.source.jobspy_sites = ["indeed", "google"]
        with patch.dict("sys.modules", {"jobspy": fake_module}):
            with patch.object(
                JobSpyScraper,
                "_normalize_rows",
                return_value=[
                    {
                        "title": "Python Developer",
                        "company": "Acme",
                        "location": "New York, NY",
                        "description": "Email your resume to hiring@example.com",
                        "job_url": "https://example.com/job",
                        "site": "indeed",
                        "salary": "$100000",
                        "date_posted": "2026-01-01",
                    }
                ],
            ):
                jobs = JobSpyScraper(config).fetch_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0][0].source, "indeed")
        self.assertEqual(jobs[0][0].apply_method, "email")
        self.assertEqual(jobs[0][0].hiring_manager_email, "hiring@example.com")

    def test_jobspy_normalizes_nan_company_to_unknown_employer(self) -> None:
        fake_module = types.SimpleNamespace(scrape_jobs=lambda **_kwargs: [{"unused": True}])
        config = JobBotConfig()
        with patch.dict("sys.modules", {"jobspy": fake_module}):
            with patch.object(
                JobSpyScraper,
                "_normalize_rows",
                return_value=[
                    {
                        "title": "Marketing Director",
                        "company": "nan",
                        "location": "New York, NY",
                        "description": "Lead campaigns",
                        "job_url": "https://example.com/job",
                        "site": "indeed",
                    }
                ],
            ):
                jobs = JobSpyScraper(config).fetch_jobs()
        self.assertEqual(jobs[0][0].employer, "Unknown Employer")

    def test_router_dispatches_jobspy(self) -> None:
        config = JobBotConfig()
        config.source.provider = "jobspy"
        router = ScraperRouter(config)
        router.fetch_jobs = router.fetch_jobs.__get__(router, ScraperRouter)
        with patch("scrapers.scraper_router.JobSpyScraper.fetch_jobs", return_value=[]) as fetch_mock:
            self.assertEqual(router.fetch_jobs(), [])
            fetch_mock.assert_called_once()

    def test_jobspy_missing_dependency_raises_clear_error(self) -> None:
        config = JobBotConfig()
        config.source.provider = "jobspy"
        with patch.dict("sys.modules", {"jobspy": None}):
            with self.assertRaisesRegex(RuntimeError, "JobSpy is not installed"):
                JobSpyScraper(config).fetch_jobs()
