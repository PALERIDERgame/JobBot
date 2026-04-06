from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from config import JobBotConfig
from database import Job
from match_scorer import MatchScorer
from resume_parser import ResumeData


class MatchScorerTests(unittest.TestCase):
    def test_missing_api_key_returns_error_state(self) -> None:
        scorer = MatchScorer(JobBotConfig())
        job = Job(
            id="1",
            title="Python Developer",
            employer="Acme",
            location="Remote",
            salary_range="",
            description_full="Python role",
            apply_method="board",
            apply_url="https://example.com",
            hiring_manager_email="",
            source="usajobs",
            posted_at="",
            scraped_at="",
        )
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python"], ["Built APIs"])
        result = scorer.score_job(job, resume)
        self.assertEqual(result.status, "error")

    def test_json_response_sets_match(self) -> None:
        config = JobBotConfig(anthropic_api_key="test")
        scorer = MatchScorer(config)
        scorer.client = MagicMock()
        scorer.client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text='{"score": 88, "rationale": "Strong fit", "strengths": ["Python"], "gaps": ["AWS"]}')]
        )
        job = Job("1", "Python Developer", "Acme", "Remote", "", "Python role", "board", "https://example.com", "", "usajobs", "", "")
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python"], ["Built APIs"])
        result = scorer.score_job(job, resume)
        self.assertTrue(result.is_match)
        self.assertEqual(result.score, 88)
