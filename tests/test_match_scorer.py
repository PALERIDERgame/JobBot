from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from config import JobBotConfig
from database import Job
from match_scorer import MatchScorer
from resume_parser import ResumeData


class MatchScorerTests(unittest.TestCase):
    def test_missing_strong_provider_returns_error_state(self) -> None:
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
        result = scorer.strong_evaluate(job, resume)
        self.assertEqual(result.status, "error")

    def test_strong_json_response_sets_apply_candidate(self) -> None:
        config = JobBotConfig(strong_stage_provider="anthropic", strong_stage_model="claude-sonnet-4-20250514", anthropic_api_key="test")
        scorer = MatchScorer(config)
        scorer._build_client = MagicMock(return_value=object())
        scorer._create_completion_with_usage = MagicMock(return_value=('{"score": 88, "confidence": 0.91, "rationale": "Strong fit", "strengths": ["Python"], "gaps": ["AWS"]}', 1000, 100))
        job = Job("1", "Python Developer", "Acme", "Remote", "", "Python role", "board", "https://example.com", "", "usajobs", "", "")
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python"], ["Built APIs"])
        result = scorer.strong_evaluate(job, resume)
        self.assertEqual(result.decision, "apply_candidate")
        self.assertEqual(result.score, 88)

    def test_openai_provider_uses_selected_key(self) -> None:
        config = JobBotConfig(strong_stage_provider="openai", strong_stage_model="gpt-5-mini", openai_api_key="openai-test")
        scorer = MatchScorer(config)
        scorer._build_client = MagicMock(return_value=object())
        scorer._create_completion_with_usage = MagicMock(return_value=('{"score": 81, "confidence": 0.83, "rationale": "Good fit", "strengths": ["APIs"], "gaps": ["Kubernetes"]}', 500, 120))
        job = Job("1", "Python Developer", "Acme", "Remote", "", "Python role", "board", "https://example.com", "", "usajobs", "", "")
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python"], ["Built APIs"])
        result = scorer.strong_evaluate(job, resume)
        self.assertEqual(result.score, 81)
        self.assertEqual(result.decision, "apply_candidate")

    def test_cheap_stage_rejects_confident_low_score(self) -> None:
        config = JobBotConfig(cheap_stage_provider="openai", cheap_stage_model="gpt-5-nano", openai_api_key="openai-test")
        scorer = MatchScorer(config)
        scorer._build_client = MagicMock(return_value=object())
        scorer._create_completion_with_usage = MagicMock(return_value=('{"score": 40, "confidence": 0.92, "rationale": "Mismatch", "strengths": [], "gaps": ["Missing core stack"]}', 300, 80))
        job = Job("1", "Python Developer", "Acme", "Remote", "", "Python role", "board", "https://example.com", "", "usajobs", "", "")
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python"], ["Built APIs"])
        result = scorer.cheap_evaluate(job, resume)
        self.assertEqual(result.decision, "reject")

    def test_confidence_label_is_coerced_to_numeric(self) -> None:
        config = JobBotConfig(strong_stage_provider="openai", strong_stage_model="gpt-5-mini", openai_api_key="openai-test")
        scorer = MatchScorer(config)
        scorer._build_client = MagicMock(return_value=object())
        scorer._create_completion_with_usage = MagicMock(return_value=('{"score": 81, "confidence": "Moderate", "rationale": "Good fit", "strengths": ["Policy"], "gaps": []}', 500, 120))
        job = Job("1", "Policy Analyst", "Acme", "New York, NY", "", "Policy role", "board", "https://example.com", "", "jobspy", "", "")
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Policy analyst", ["Policy"], ["Built programs"])
        result = scorer.strong_evaluate(job, resume)
        self.assertEqual(result.status, "scored")
        self.assertAlmostEqual(result.confidence or 0.0, 0.6)

    def test_suggest_job_keywords_returns_space_separated_terms(self) -> None:
        config = JobBotConfig(cheap_stage_provider="openai", cheap_stage_model="gpt-5-nano", openai_api_key="openai-test")
        scorer = MatchScorer(config)
        scorer._build_client = MagicMock(return_value=object())
        scorer._create_completion = MagicMock(return_value='{"keywords": ["python developer", "automation", "llm tools", "api integration"]}')
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python", "Automation"], ["Built APIs"])
        result = scorer.suggest_job_keywords(resume)
        self.assertEqual(result, "python developer automation llm tools api integration")
