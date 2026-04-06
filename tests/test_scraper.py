from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from config import JobBotConfig
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
