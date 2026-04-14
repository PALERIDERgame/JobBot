from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from config import JobBotConfig
from database import Job
from document_tailoring import DocumentTailoringPayload
from match_scorer import MatchScorer, TfidfVectorizer
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

    def test_build_cheap_prompt_includes_location_and_salary_screening_constraints(self) -> None:
        config = JobBotConfig()
        config.source.location = "New York, NY"
        config.salary_floor = 90000
        scorer = MatchScorer(config)
        job = Job("1", "Python Developer", "Acme", "Remote", "$85,000 - $95,000", "Python role", "board", "https://example.com", "", "usajobs", "", "")
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python"], ["Built APIs"])
        prompt = scorer._build_cheap_prompt(job, resume, force_escalate=False)
        screening = prompt["screening_constraints"]
        self.assertEqual(screening["target_location"], "New York, NY")
        self.assertEqual(screening["salary_floor_usd"], 90000)
        self.assertIn("same metro area", screening["location_note"])
        self.assertIn("annualised", screening["salary_note"])

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

    def test_precheap_gate_rejects_low_similarity(self) -> None:
        if TfidfVectorizer is None:
            self.skipTest("scikit-learn not available")
        config = JobBotConfig(precheap_gate_enabled=True, precheap_gate_reject_threshold=30)
        scorer = MatchScorer(config)
        job = Job("1", "Chef", "Acme", "Remote", "", "Kitchen prep and cooking duties.", "board", "", "", "jobspy", "", "")
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python", "APIs"], ["Built APIs"])
        result = scorer.precheap_gate(job, resume)
        self.assertEqual(result.decision, "reject")

    def test_precheap_gate_passes_with_overlap(self) -> None:
        if TfidfVectorizer is None:
            self.skipTest("scikit-learn not available")
        config = JobBotConfig(precheap_gate_enabled=True, precheap_gate_reject_threshold=30)
        scorer = MatchScorer(config)
        job = Job(
            "1",
            "Python Developer",
            "Acme",
            "Remote",
            "",
            "Looking for Python, APIs, and automation experience.",
            "board",
            "",
            "",
            "jobspy",
            "",
            "",
        )
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python", "Automation"], ["Built APIs"])
        result = scorer.precheap_gate(job, resume)
        self.assertEqual(result.decision, "pass")

    def test_fast_rank_prefers_relevant_python_role(self) -> None:
        scorer = MatchScorer(JobBotConfig())
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python", "Automation"], ["Built APIs and automation systems"])
        relevant = Job("1", "Python Developer", "Acme", "Remote", "", "Python APIs automation", "board", "", "", "jobspy", "", "")
        irrelevant = Job("2", "Retail Store Manager", "Acme", "Remote", "", "Retail scheduling and merchandising", "board", "", "", "jobspy", "", "")
        relevant_rank = scorer.fast_rank_job(relevant, resume)
        irrelevant_rank = scorer.fast_rank_job(irrelevant, resume)
        self.assertGreater(relevant_rank.score, irrelevant_rank.score)

    def test_fast_rank_applies_salary_penalty(self) -> None:
        config = JobBotConfig(salary_floor=150000)
        scorer = MatchScorer(config)
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python"], ["Built APIs"])
        low_salary = Job("1", "Python Developer", "Acme", "Remote", "$90,000 - $110,000", "Python role", "board", "", "", "jobspy", "", "")
        high_salary = Job("2", "Python Developer", "Acme", "Remote", "$160,000 - $180,000", "Python role", "board", "", "", "jobspy", "", "")
        self.assertGreater(scorer.fast_rank_job(high_salary, resume).score, scorer.fast_rank_job(low_salary, resume).score)

    def test_fast_rank_force_escalate_keyword_boosts_score(self) -> None:
        config = JobBotConfig(force_escalate_keywords=["agentic"])
        scorer = MatchScorer(config)
        resume = ResumeData("", "", "Jane", "jane@example.com", "", "Python engineer", ["Python"], ["Built APIs"])
        plain = Job("1", "Software Engineer", "Acme", "Remote", "", "General backend work", "board", "", "", "jobspy", "", "")
        boosted = Job("2", "Software Engineer", "Acme", "Remote", "", "General backend work with agentic systems", "board", "", "", "jobspy", "", "")
        self.assertGreater(scorer.fast_rank_job(boosted, resume).score, scorer.fast_rank_job(plain, resume).score)

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
        scorer._create_doc_tailoring_completion = MagicMock(
            return_value=(
                '{"work_entries":[{"role_line":"Role 1","date_line":"2024","bullets":["Improved reporting cadence and dashboard visibility."]}],"key_skills":["Dashboard Reporting","Lead Generation"],"cover_letter_text":"Dear Hiring Team at Acme,\\n\\nTest letter.\\n\\nSincerely,\\nJane"}',
                {"mode": "json_schema", "shape_summary": "message(output_text)", "text_length": 250},
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
        scorer._create_doc_tailoring_completion = MagicMock(
            return_value=(
                '{"work_entries":[{"role_line":"Role 1","date_line":"2024","bullets":["Built dashboards for leadership."]}],"key_skills":["Dashboard Reporting"],"cover_letter_text":"Letter"}',
                {"mode": "json_schema", "shape_summary": "message(output_text)", "text_length": 180},
            )
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
        scorer._create_doc_tailoring_completion.assert_called_once()
        self.assertEqual(scorer._create_doc_tailoring_completion.call_args[0][1], "gpt-5-mini")

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

    def test_create_doc_tailoring_completion_extracts_structured_payload_from_model_dump(self) -> None:
        config = JobBotConfig(doc_stage_provider="openai", doc_stage_model="gpt-5-mini", openai_api_key="openai-test")
        scorer = MatchScorer(config)

        class FakeResponse:
            output = []

            def model_dump(self, mode: str = "python") -> dict[str, object]:
                return {
                    "output": [
                        {
                            "type": "message",
                            "content": [],
                        }
                    ],
                    "response": {
                        "work_entries": [
                            {"role_line": "Role 1", "date_line": "2024", "bullets": ["Built dashboards for leadership."]}
                        ],
                        "key_skills": ["Dashboard Reporting"],
                        "cover_letter_text": "Letter",
                    },
                }

        fake_client = MagicMock()
        fake_client.responses.create.return_value = FakeResponse()
        scorer._build_client = MagicMock(return_value=fake_client)

        text, meta = scorer._create_doc_tailoring_completion(
            "openai",
            "gpt-5-mini",
            {"job": "test"},
            system_prompt="Return JSON",
        )
        payload = json.loads(text)
        self.assertEqual(payload["key_skills"], ["Dashboard Reporting"])
        self.assertEqual(meta["mode"], "json_schema")

    def test_create_doc_tailoring_completion_extracts_text_content_fallback(self) -> None:
        config = JobBotConfig(doc_stage_provider="openai", doc_stage_model="gpt-5-mini", openai_api_key="openai-test")
        scorer = MatchScorer(config)

        class Content:
            def __init__(self, text: str) -> None:
                self.type = "output_text"
                self.text = text

        class OutputItem:
            def __init__(self, text: str) -> None:
                self.type = "message"
                self.content = [Content(text)]

        class FakeResponse:
            def __init__(self, text: str) -> None:
                self.output = [OutputItem(text)]

        fake_client = MagicMock()
        fake_client.responses.create.return_value = FakeResponse('{"work_entries":[],"key_skills":[],"cover_letter_text":"Letter"}')
        scorer._build_client = MagicMock(return_value=fake_client)

        text, meta = scorer._create_doc_tailoring_completion(
            "openai",
            "gpt-5-mini",
            {"job": "test"},
            system_prompt="Return JSON",
        )
        self.assertEqual(json.loads(text)["cover_letter_text"], "Letter")
        self.assertEqual(meta["mode"], "text_fallback")

    def test_tailor_documents_with_ai_reports_no_extractable_text(self) -> None:
        config = JobBotConfig(doc_stage_provider="openai", doc_stage_model="gpt-5-mini", openai_api_key="openai-test")
        scorer = MatchScorer(config)
        scorer._build_client = MagicMock(return_value=object())
        scorer._create_doc_tailoring_completion = MagicMock(
            return_value=("", {"mode": "text_fallback", "shape_summary": "no-output-items", "text_length": 0})
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
            work_experience_entries=[ResumeWorkEntry("Role 1", "2024", ["Built dashboards"])],
        )
        attempt = scorer.tailor_documents_with_ai(
            Job("1", "Head of Marketing", "Acme", "Remote", "", "Lead B2B growth", "board", "", "", "jobspy", "", ""),
            resume,
            DocumentTailoringPayload(work_entries=resume.work_experience_entries, key_skills=["Python"], cover_letter_text="Local"),
        )
        self.assertTrue(attempt.attempted)
        self.assertEqual(attempt.failure_reason, "OpenAI response did not contain extractable text.")

    def test_tailor_documents_with_ai_reports_invalid_json(self) -> None:
        config = JobBotConfig(doc_stage_provider="openai", doc_stage_model="gpt-5-mini", openai_api_key="openai-test")
        scorer = MatchScorer(config)
        scorer._build_client = MagicMock(return_value=object())
        scorer._create_doc_tailoring_completion = MagicMock(
            return_value=("not json at all", {"mode": "text_fallback", "shape_summary": "message(output_text)", "text_length": 14})
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
            work_experience_entries=[ResumeWorkEntry("Role 1", "2024", ["Built dashboards"])],
        )
        attempt = scorer.tailor_documents_with_ai(
            Job("1", "Head of Marketing", "Acme", "Remote", "", "Lead B2B growth", "board", "", "", "jobspy", "", ""),
            resume,
            DocumentTailoringPayload(work_entries=resume.work_experience_entries, key_skills=["Python"], cover_letter_text="Local"),
        )
        self.assertTrue(attempt.attempted)
        self.assertEqual(attempt.failure_reason, "OpenAI response could not be parsed as JSON.")
