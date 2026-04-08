from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from config import JobBotConfig
from database import Job
from document_tailoring import DocumentTailoringPayload
from match_scorer import MatchScorer
from resume_parser import ResumeData, ResumeWorkEntry


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

    def test_tailor_documents_with_ai_returns_structured_payload(self) -> None:
        config = JobBotConfig(doc_stage_provider="openai", doc_stage_model="gpt-5-mini", openai_api_key="openai-test")
        scorer = MatchScorer(config)
        scorer._build_client = MagicMock(return_value=object())
        scorer._create_completion = MagicMock(
            return_value=(
                '{"work_entries":[{"role_line":"Role 1","date_line":"2024","bullets":["Improved reporting cadence and dashboard visibility."]}],'
                '"key_skills":["Dashboard Reporting","Lead Generation"],'
                '"cover_letter_text":"Dear Hiring Team at Acme,\\n\\nTest letter.\\n\\nSincerely,\\nJane"}'
            )
        )
        job = Job("1", "Head of Marketing", "Acme", "Remote", "", "Lead B2B growth and reporting.", "board", "https://example.com", "", "jobspy", "", "")
        resume = ResumeData(
            "",
            "",
            "Jane",
            "jane@example.com",
            "",
            "Python engineer",
            ["Python"],
            ["Built APIs"],
            work_experience_entries=[ResumeWorkEntry("Role 1", "2024", ["Built dashboards for leadership"])],
        )
        local = DocumentTailoringPayload(
            work_entries=[ResumeWorkEntry("Role 1", "2024", ["Built dashboards for leadership"])],
            key_skills=["Python"],
            cover_letter_text="Local",
        )
        attempt = scorer.tailor_documents_with_ai(job, resume, local, alignment_notes="Strong fit")
        self.assertTrue(attempt.attempted)
        self.assertIsNotNone(attempt.payload)
        assert attempt.payload is not None
        self.assertEqual(attempt.payload.route, "openai")
        self.assertEqual(attempt.payload.work_entries[0].bullets[0], "Improved reporting cadence and dashboard visibility.")
        self.assertIn("Lead Generation", attempt.payload.key_skills)

    def test_tailor_documents_with_ai_ignores_non_openai_provider(self) -> None:
        config = JobBotConfig(doc_stage_provider="anthropic", doc_stage_model="claude-sonnet-4-20250514", anthropic_api_key="anthropic-test")
        scorer = MatchScorer(config)
        attempt = scorer.tailor_documents_with_ai(
            Job("1", "Head of Marketing", "Acme", "Remote", "", "Lead B2B growth and reporting.", "board", "", "", "jobspy", "", ""),
            ResumeData("", "", "Jane", "jane@example.com", "", "Summary", ["Python"], ["Built APIs"]),
            DocumentTailoringPayload(),
        )
        self.assertFalse(attempt.attempted)
        self.assertIsNone(attempt.payload)

    def test_tailor_documents_with_ai_uses_doc_stage_model_not_cheap_stage_model(self) -> None:
        config = JobBotConfig(
            cheap_stage_provider="ollama_local",
            cheap_stage_model="qwen2.5:7b",
            doc_stage_provider="openai",
            doc_stage_model="gpt-5-mini",
            openai_api_key="openai-test",
        )
        scorer = MatchScorer(config)
        scorer._build_client = MagicMock(return_value=object())
        scorer._create_completion = MagicMock(
            return_value='{"work_entries":[{"role_line":"Role 1","date_line":"2024","bullets":["Built dashboards for leadership."]}],"key_skills":["Dashboard Reporting"],"cover_letter_text":"Letter"}'
        )
        resume = ResumeData(
            "",
            "",
            "Jane",
            "jane@example.com",
            "",
            "Summary",
            ["Python"],
            ["Built APIs"],
            work_experience_entries=[ResumeWorkEntry("Role 1", "2024", ["Built dashboards for leadership"])],
        )
        attempt = scorer.tailor_documents_with_ai(
            Job("1", "Head of Marketing", "Acme", "Remote", "", "Lead B2B growth and reporting.", "board", "", "", "jobspy", "", ""),
            resume,
            DocumentTailoringPayload(work_entries=resume.work_experience_entries, key_skills=["Python"], cover_letter_text="Local"),
        )
        self.assertTrue(attempt.attempted)
        scorer._create_completion.assert_called_once()
        self.assertEqual(scorer._create_completion.call_args[0][1], "gpt-5-mini")

    def test_tailor_documents_with_ai_rejects_invalid_openai_model_mismatch(self) -> None:
        config = JobBotConfig(
            doc_stage_provider="openai",
            doc_stage_model="qwen2.5:7b",
            openai_api_key="openai-test",
        )
        scorer = MatchScorer(config)
        attempt = scorer.tailor_documents_with_ai(
            Job("1", "Head of Marketing", "Acme", "Remote", "", "Lead B2B growth and reporting.", "board", "", "", "jobspy", "", ""),
            ResumeData("", "", "Jane", "jane@example.com", "", "Summary", ["Python"], ["Built APIs"]),
            DocumentTailoringPayload(),
        )
        self.assertFalse(attempt.attempted)
        self.assertIn("model mismatch", attempt.failure_reason.lower())

    def test_extract_json_text_recovers_markdown_wrapped_json(self) -> None:
        cleaned = MatchScorer._extract_json_text("```json\nbefore\n{\"key\": 1}\nafter\n```")
        self.assertEqual(cleaned, '{"key": 1}')
