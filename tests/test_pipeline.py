from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config import build_app_paths, load_or_create_config
from database import Database, Job
from document_tailoring import DocumentTailoringAttempt, DocumentTailoringPayload
from match_scorer import StageEvaluation
from pipeline import JobBotPipeline
from resume_parser import ResumeData, ResumeWorkEntry
from test_support import workspace_temp_dir


class PipelineTests(unittest.TestCase):
    def test_prepare_document_tailoring_records_specific_parse_failure_and_retry_count(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                pipeline = JobBotPipeline(config, paths, database)
                local_payload = DocumentTailoringPayload(
                    work_entries=[ResumeWorkEntry("Role 1", "2024", ["Built dashboards"])],
                    key_skills=["Dashboard Reporting"],
                    cover_letter_text="Local",
                )
                resume = ResumeData(
                    "", "", "Jane", "jane@example.com", "", "Summary", ["Dashboard Reporting"], ["Built dashboards"],
                    work_experience_entries=local_payload.work_entries,
                )
                job = Job("1", "Head of Marketing", "Acme", "Remote", "", "Lead B2B growth", "board", "", "", "jobspy", "", "")
                score = StageEvaluation(
                    "strong", "openai", "gpt-5-mini", "scored", "review", 80, 0.8, "Good fit", [], [], 0, 0, 0.0, "", ""
                ).to_match_score(config.final_apply_threshold)
                pipeline.doc_generator.build_local_tailoring_payload = lambda *args, **kwargs: local_payload
                pipeline.doc_generator.should_escalate_tailoring = lambda *args, **kwargs: True
                pipeline.scorer.tailor_documents_with_ai = lambda *args, **kwargs: DocumentTailoringAttempt(
                    attempted=True,
                    provider="openai",
                    model="gpt-5-mini",
                    failure_reason="OpenAI response could not be parsed as JSON.",
                    retry_count=kwargs.get("retry_count", 0),
                )

                payload = pipeline._prepare_document_tailoring(job, resume, score, ai_notes="")
                self.assertEqual(payload.route, "fallback")
                self.assertTrue(payload.ai_attempted)
                self.assertEqual(payload.provider, "openai")
                self.assertEqual(payload.model, "gpt-5-mini")
                self.assertEqual(payload.retry_count, 1)
                self.assertIn("parsed as json", payload.fallback_reason.lower())

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
                self.assertTrue(row["generated_at"])

    def test_generate_documents_for_job_emits_progress_events(self) -> None:
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
                    id="70",
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

                def fake_generate(output_dir, job, resume, score, *, ai_notes="", tailoring_payload=None, progress_callback=None):
                    if progress_callback:
                        progress_callback("tailoring_resume", "Tailoring resume...", 3)
                        progress_callback("exporting_pdf", "Exporting PDF...", 4)
                        progress_callback("validating_pages", "Validating final page count...", 5)
                        progress_callback("writing_cover_letter", "Writing cover letter...", 6)
                    target_dir = output_dir / "Acme_2026-01-01_deadbeef"
                    target_dir.mkdir(parents=True, exist_ok=True)
                    resume_pdf = target_dir / "resume.pdf"
                    cover = target_dir / "cover_letter.txt"
                    resume_pdf.write_text("pdf", encoding="utf-8")
                    cover.write_text("cover", encoding="utf-8")
                    from doc_generator import GeneratedDocs
                    return GeneratedDocs(output_dir=target_dir, resume_pdf_path=resume_pdf, cover_letter_path=cover)

                pipeline.doc_generator.generate = fake_generate
                events: list[tuple[str, str, int]] = []
                pipeline.generate_documents_for_job("70", progress_callback=lambda stage, message, progress: events.append((stage, message, progress)))
                self.assertEqual(
                    [stage for stage, _message, _progress in events],
                    ["starting", "loading_job", "parsing_resume", "tailoring_resume", "exporting_pdf", "validating_pages", "writing_cover_letter", "saving_database_state", "completed"],
                )

    def test_generate_documents_for_job_records_page_limit_failure(self) -> None:
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
                    id="71",
                    title="Director of Ecommerce",
                    employer="MILK BAR",
                    location="New York, NY",
                    salary_range="",
                    description_full="Lead ecommerce growth, reporting, and site optimization.",
                    apply_method="board",
                    apply_url="https://example.com",
                    hiring_manager_email="",
                    source="jobspy",
                    posted_at="2026-01-01T00:00:00+00:00",
                    scraped_at="2026-01-01T00:00:00+00:00",
                )
                pipeline.scraper.fetch_jobs = lambda: [(sample_job, {"sample": True})]
                pipeline.run()

                from doc_generator import GeneratedDocs

                def fake_generate(output_dir, job, resume, score, *, ai_notes="", tailoring_payload=None, progress_callback=None):
                    if progress_callback:
                        progress_callback("tailoring_resume", "Tailoring resume...", 3)
                        progress_callback("exporting_pdf", "Exporting PDF...", 4)
                        progress_callback("validating_pages", "Validating final page count...", 5)
                    return GeneratedDocs(
                        output_dir=output_dir,
                        resume_pdf_path=Path(),
                        cover_letter_path=Path(),
                        resume_docx_path=Path(),
                        status="failed",
                        error_message="JobBot could not compress the tailored resume to 2 pages.",
                    )

                pipeline.doc_generator.generate = fake_generate
                with self.assertRaisesRegex(ValueError, "compress the tailored resume to 2 pages"):
                    pipeline.generate_documents_for_job("71")
                row = database.get_review_row("71")
                self.assertEqual(row["document_status"], "failed")
                self.assertIn("compress the tailored resume to 2 pages", row["document_error"].lower())

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

    def test_load_resume_reparses_docx_cache_without_template_metadata(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                from docx import Document

                paths = build_app_paths()
                config = load_or_create_config(paths)
                resume_path = Path(tmp) / "Robert Thom Resume 2026.docx"
                doc = Document()
                doc.add_paragraph("ROBERT THOM")
                doc.add_paragraph("robert@example.com | linkedin.com/in/example | (530) 220-4847")
                doc.add_paragraph("WORK EXPERIENCE", style="Heading 1")
                doc.add_paragraph("Underdog Strategies, New York, NY — Digital Advertising and Field Manager", style="Heading 2")
                doc.add_paragraph("JULY 2024 - Present")
                bullet = doc.add_paragraph(style="List Bullet")
                bullet.add_run("Led digital ad strategy and reporting")
                doc.add_paragraph("EDUCATION", style="Heading 1")
                doc.add_paragraph("University of California, Davis", style="Heading 2")
                doc.add_paragraph("KEY SKILLS", style="Heading 1")
                doc.add_paragraph("Operations, Project Management, CRM, Data Analysis")
                doc.save(str(resume_path))

                config.resume_source_path = str(resume_path)
                paths.resume_json.write_text(
                    (
                        '{'
                        f'"source_path": "{str(resume_path).replace("\\", "\\\\")}", '
                        '"raw_text": "legacy", '
                        '"name": "WORK EXPERIENCE", '
                        '"email": "old@example.com", '
                        '"phone": "555", '
                        '"summary": "legacy", '
                        '"skills": ["legacy"], '
                        '"experience_lines": ["legacy"], '
                        '"header_lines": ["robert@example.com | linkedin.com/in/example | (530) 220-4847"], '
                        '"education_lines": ["University of California, Davis"], '
                        '"key_skills_lines": ["Operations, Project Management, CRM, Data Analysis"], '
                        '"work_experience_entries": [{"role_line": "Underdog Strategies, New York, NY — Digital Advertising and Field Manager", "date_line": "JULY 2024 - Present", "bullets": ["Led digital ad strategy and reporting"]}]'
                        '}'
                    ),
                    encoding="utf-8",
                )
                database = Database(paths.database_file)
                database.initialize()
                pipeline = JobBotPipeline(config, paths, database)
                resume = pipeline._load_resume()
                self.assertEqual(resume.name, "ROBERT THOM")
                self.assertTrue(resume.key_skills_templates)
                self.assertTrue(resume.work_experience_entries[0].role_template is not None)
                self.assertTrue(resume.work_experience_entries[0].bullet_templates)

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
