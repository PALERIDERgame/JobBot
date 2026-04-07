from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config import build_app_paths, load_or_create_config
from database import Database, Job
from match_scorer import StageEvaluation
from pipeline import JobBotPipeline
from test_support import workspace_temp_dir


class PipelineTests(unittest.TestCase):
    def test_pipeline_records_completed_run(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                resume_path = Path(tmp) / "resume.txt"
                resume_path.write_text(
                    "Jane Candidate\njane@example.com\n555-123-4567\nSummary: Python engineer\nSkills: Python, SQL\nBuilt APIs\n",
                    encoding="utf-8",
                )
                config.resume_source_path = str(resume_path)
                config.cheap_stage_provider = "openai"
                config.strong_stage_provider = "openai"
                database = Database(paths.database_file)
                database.initialize()
                pipeline = JobBotPipeline(config, paths, database)
                sample_job = Job(
                    id="1",
                    title="Python Developer",
                    employer="Acme",
                    location="Remote",
                    salary_range="100-120",
                    description_full="Build APIs",
                    apply_method="board",
                    apply_url="https://example.com",
                    hiring_manager_email="",
                    source="usajobs",
                    posted_at="2026-01-01T00:00:00+00:00",
                    scraped_at="2026-01-01T00:00:00+00:00",
                )
                pipeline.scraper.fetch_jobs = lambda: [(sample_job, {"sample": True})]
                pipeline.scorer.cheap_evaluate = lambda job, resume, force_escalate=False: StageEvaluation(
                    "cheap", "openai", "gpt-5-nano", "scored", "escalate", 72, 0.8, "Promising", ["Python"], ["AWS"], 100, 10, 0.0001, "", "2026-01-01T00:00:00+00:00"
                )
                pipeline.scorer.strong_evaluate = lambda job, resume: StageEvaluation(
                    "strong", "openai", "gpt-5-mini", "scored", "apply_candidate", 91, 0.9, "Great fit", ["Python"], ["AWS"], 200, 20, 0.0002, "", "2026-01-01T00:00:00+00:00"
                )
                pipeline.scorer.document_generation_notes = lambda job, resume, strong_eval: "Tailored note"
                pipeline.gmail_client.deliver_match = lambda job, score, docs: type(
                    "Delivery",
                    (),
                    {"method": "local", "status": "skipped", "message_id": "", "error_message": ""},
                )()
                result = pipeline.run()
                self.assertEqual(result.status, "completed")
                rows = database.list_review_rows()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["delivery_status"], "pending_approval")
                self.assertEqual(rows[0]["document_status"], "pending")

    def test_auto_mode_still_sends_when_enabled(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                config.automation_mode = "auto"
                config.cheap_stage_provider = "openai"
                config.strong_stage_provider = "openai"
                resume_path = Path(tmp) / "resume.txt"
                resume_path.write_text(
                    "Jane Candidate\njane@example.com\n555-123-4567\nSummary: Python engineer\nSkills: Python, SQL\nBuilt APIs\n",
                    encoding="utf-8",
                )
                config.resume_source_path = str(resume_path)
                database = Database(paths.database_file)
                database.initialize()
                pipeline = JobBotPipeline(config, paths, database)
                sample_job = Job(
                    id="2",
                    title="Python Developer",
                    employer="Acme",
                    location="Remote",
                    salary_range="100-120",
                    description_full="Email your resume to hiring@example.com",
                    apply_method="email",
                    apply_url="https://example.com",
                    hiring_manager_email="hiring@example.com",
                    source="usajobs",
                    posted_at="2026-01-01T00:00:00+00:00",
                    scraped_at="2026-01-01T00:00:00+00:00",
                )
                pipeline.scraper.fetch_jobs = lambda: [(sample_job, {"sample": True})]
                pipeline.scorer.cheap_evaluate = lambda job, resume, force_escalate=False: StageEvaluation(
                    "cheap", "openai", "gpt-5-nano", "scored", "escalate", 72, 0.8, "Promising", ["Python"], ["AWS"], 100, 10, 0.0001, "", "2026-01-01T00:00:00+00:00"
                )
                pipeline.scorer.strong_evaluate = lambda job, resume: StageEvaluation(
                    "strong", "openai", "gpt-5-mini", "scored", "apply_candidate", 91, 0.9, "Great fit", ["Python"], ["AWS"], 200, 20, 0.0002, "", "2026-01-01T00:00:00+00:00"
                )
                pipeline.scorer.document_generation_notes = lambda job, resume, strong_eval: "Tailored note"
                pipeline.gmail_client.deliver_match = lambda job, score, docs: type(
                    "Delivery",
                    (),
                    {"method": "gmail_employer", "status": "sent", "message_id": "abc123", "error_message": ""},
                )()
                pipeline.run()
                row = database.get_review_row("2")
                self.assertEqual(row["delivery_status"], "sent")
                self.assertEqual(row["delivery_method"], "gmail_employer")
                self.assertEqual(row["apply_method"], "email")
                self.assertEqual(row["hiring_manager_email"], "hiring@example.com")

    def test_auto_mode_keeps_board_jobs_in_review_queue(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                config.automation_mode = "auto"
                config.cheap_stage_provider = "openai"
                config.strong_stage_provider = "openai"
                resume_path = Path(tmp) / "resume.txt"
                resume_path.write_text(
                    "Jane Candidate\njane@example.com\n555-123-4567\nSummary: Python engineer\nSkills: Python, SQL\nBuilt APIs\n",
                    encoding="utf-8",
                )
                config.resume_source_path = str(resume_path)
                database = Database(paths.database_file)
                database.initialize()
                pipeline = JobBotPipeline(config, paths, database)
                sample_job = Job(
                    id="3",
                    title="Python Developer",
                    employer="Acme",
                    location="Remote",
                    salary_range="100-120",
                    description_full="Apply on the company site.",
                    apply_method="board",
                    apply_url="https://example.com",
                    hiring_manager_email="",
                    source="usajobs",
                    posted_at="2026-01-01T00:00:00+00:00",
                    scraped_at="2026-01-01T00:00:00+00:00",
                )
                pipeline.scraper.fetch_jobs = lambda: [(sample_job, {"sample": True})]
                pipeline.scorer.cheap_evaluate = lambda job, resume, force_escalate=False: StageEvaluation(
                    "cheap", "openai", "gpt-5-nano", "scored", "escalate", 72, 0.8, "Promising", ["Python"], ["AWS"], 100, 10, 0.0001, "", "2026-01-01T00:00:00+00:00"
                )
                pipeline.scorer.strong_evaluate = lambda job, resume: StageEvaluation(
                    "strong", "openai", "gpt-5-mini", "scored", "apply_candidate", 91, 0.9, "Great fit", ["Python"], ["AWS"], 200, 20, 0.0002, "", "2026-01-01T00:00:00+00:00"
                )
                pipeline.scorer.document_generation_notes = lambda job, resume, strong_eval: "Tailored note"
                pipeline.gmail_client.deliver_match = lambda job, score, docs: type(
                    "Delivery",
                    (),
                    {"method": "gmail", "status": "sent", "message_id": "abc123", "error_message": ""},
                )()
                pipeline.run()
                row = database.get_review_row("3")
                self.assertEqual(row["delivery_status"], "pending_approval")
                self.assertEqual(row["apply_method"], "board")

    def test_semi_auto_can_skip_ai_scoring_and_queue_fast(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                config.automation_mode = "semi_auto"
                config.skip_ai_scoring_in_semi_auto = True
                resume_path = Path(tmp) / "resume.txt"
                resume_path.write_text(
                    "Jane Candidate\njane@example.com\n555-123-4567\nSummary: Python engineer\nSkills: Python, SQL\nBuilt APIs\n",
                    encoding="utf-8",
                )
                config.resume_source_path = str(resume_path)
                database = Database(paths.database_file)
                database.initialize()
                pipeline = JobBotPipeline(config, paths, database)
                sample_job = Job(
                    id="4",
                    title="Python Developer",
                    employer="Acme",
                    location="Remote",
                    salary_range="100-120",
                    description_full="Build APIs",
                    apply_method="board",
                    apply_url="https://example.com",
                    hiring_manager_email="",
                    source="jobspy",
                    posted_at="2026-01-01T00:00:00+00:00",
                    scraped_at="2026-01-01T00:00:00+00:00",
                )
                pipeline.scraper.fetch_jobs = lambda: [(sample_job, {"sample": True})]
                pipeline.scorer.cheap_evaluate = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cheap scorer should not run"))
                pipeline.scorer.strong_evaluate = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("strong scorer should not run"))
                result = pipeline.run()
                self.assertEqual(result.status, "completed")
                self.assertEqual(result.jobs_matched, 1)
                row = database.get_review_row("4")
                self.assertEqual(row["match_status"], "review")
                self.assertEqual(row["delivery_status"], "pending_approval")
                self.assertEqual(row["document_status"], "pending")

    def test_semi_auto_approve_requires_generated_documents(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                config.automation_mode = "semi_auto"
                config.skip_ai_scoring_in_semi_auto = True
                resume_path = Path(tmp) / "resume.txt"
                resume_path.write_text(
                    "Jane Candidate\njane@example.com\n555-123-4567\nSummary: Python engineer\nSkills: Python, SQL\nBuilt APIs\n",
                    encoding="utf-8",
                )
                config.resume_source_path = str(resume_path)
                database = Database(paths.database_file)
                database.initialize()
                pipeline = JobBotPipeline(config, paths, database)
                sample_job = Job(
                    id="6",
                    title="Python Developer",
                    employer="Acme",
                    location="Remote",
                    salary_range="100-120",
                    description_full="Build APIs",
                    apply_method="board",
                    apply_url="https://example.com",
                    hiring_manager_email="",
                    source="jobspy",
                    posted_at="2026-01-01T00:00:00+00:00",
                    scraped_at="2026-01-01T00:00:00+00:00",
                )
                pipeline.scraper.fetch_jobs = lambda: [(sample_job, {"sample": True})]
                pipeline.run()
                with self.assertRaisesRegex(ValueError, "Generate documents first"):
                    pipeline.approve_and_send("6")

    def test_generate_documents_for_job_creates_files(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                config.automation_mode = "semi_auto"
                config.skip_ai_scoring_in_semi_auto = True
                resume_path = Path(tmp) / "resume.txt"
                resume_path.write_text(
                    "Jane Candidate\njane@example.com\n555-123-4567\nSummary: Python engineer\nSkills: Python, SQL\nBuilt APIs\n",
                    encoding="utf-8",
                )
                config.resume_source_path = str(resume_path)
                database = Database(paths.database_file)
                database.initialize()
                pipeline = JobBotPipeline(config, paths, database)
                sample_job = Job(
                    id="7",
                    title="Python Developer",
                    employer="Acme",
                    location="Remote",
                    salary_range="100-120",
                    description_full="Build APIs",
                    apply_method="board",
                    apply_url="https://example.com",
                    hiring_manager_email="",
                    source="jobspy",
                    posted_at="2026-01-01T00:00:00+00:00",
                    scraped_at="2026-01-01T00:00:00+00:00",
                )
                pipeline.scraper.fetch_jobs = lambda: [(sample_job, {"sample": True})]
                pipeline.run()
                docs = pipeline.generate_documents_for_job("7")
                self.assertTrue(docs.output_dir.exists())
                self.assertTrue(docs.resume_pdf_path.exists())
                self.assertTrue(docs.cover_letter_path.exists())
                row = database.get_review_row("7")
                self.assertEqual(row["document_status"], "generated")

    def test_load_resume_reparses_legacy_cache_without_structured_sections(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                resume_path = Path(tmp) / "resume.txt"
                resume_path.write_text(
                    "ROBERT THOM\nrobert@example.com | linkedin.com/in/example | (530) 220-4847\n"
                    "WORK EXPERIENCE\n"
                    "Underdog Strategies, New York, NY — Digital Advertising and Field Manager\n"
                    "JULY 2024 - Present\n"
                    "● Led digital ad strategy and reporting.\n"
                    "EDUCATION\n"
                    "University of California, Davis\n"
                    "Bachelor of Arts in Political Science Class of 2015\n"
                    "KEY SKILLS\n"
                    "Operations, Project Management, CRM, Data Analysis\n",
                    encoding="utf-8",
                )
                config.resume_source_path = str(resume_path)
                paths.resume_json.write_text(
                    '{"source_path": "' + str(resume_path).replace("\\", "\\\\") + '", "raw_text": "legacy", "name": "ROBERT THOM", "email": "old@example.com", "phone": "555", "summary": "legacy", "skills": ["legacy"], "experience_lines": ["legacy"]}',
                    encoding="utf-8",
                )
                database = Database(paths.database_file)
                database.initialize()
                pipeline = JobBotPipeline(config, paths, database)
                resume = pipeline._load_resume()
                self.assertTrue(resume.header_lines)
                self.assertTrue(resume.education_lines)
                self.assertTrue(resume.work_experience_entries)

    def test_recent_duplicate_from_prior_day_window_is_skipped(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                config.automation_mode = "semi_auto"
                config.skip_ai_scoring_in_semi_auto = True
                resume_path = Path(tmp) / "resume.txt"
                resume_path.write_text(
                    "Jane Candidate\njane@example.com\n555-123-4567\nSummary: Python engineer\nSkills: Python, SQL\nBuilt APIs\n",
                    encoding="utf-8",
                )
                config.resume_source_path = str(resume_path)
                database = Database(paths.database_file)
                database.initialize()
                existing_job = Job(
                    id="5",
                    title="Python Developer",
                    employer="Acme",
                    location="Remote",
                    salary_range="100-120",
                    description_full="Build APIs",
                    apply_method="board",
                    apply_url="https://example.com",
                    hiring_manager_email="",
                    source="jobspy",
                    posted_at="2026-01-01T00:00:00+00:00",
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                )
                database.upsert_job(existing_job, {"sample": True})
                pipeline = JobBotPipeline(config, paths, database)
                incoming_job = Job(
                    id="5",
                    title="Python Developer",
                    employer="Acme",
                    location="Remote",
                    salary_range="100-120",
                    description_full="Build APIs",
                    apply_method="board",
                    apply_url="https://example.com",
                    hiring_manager_email="",
                    source="jobspy",
                    posted_at="2026-01-01T00:00:00+00:00",
                    scraped_at="2026-01-01T00:00:00+00:00",
                )
                pipeline.scraper.fetch_jobs = lambda: [(incoming_job, {"sample": True})]
                result = pipeline.run()
                self.assertEqual(result.status, "completed")
                self.assertEqual(result.jobs_matched, 0)
