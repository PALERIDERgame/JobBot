from __future__ import annotations

import os
import tkinter as tk
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from config import build_app_paths, load_or_create_config
from database import Database
from dashboard import JobBotDashboard
from doc_generator import GeneratedDocs
from database import Job
from test_support import workspace_temp_dir


class DashboardSmokeTests(unittest.TestCase):
    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_dashboard_dependencies_initialize(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                self.assertEqual(config.source.provider, "jobspy")

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_autosave_persists_field_updates(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                root = tk.Tk()
                root.withdraw()
                try:
                    dashboard = JobBotDashboard(root, config, paths, database)
                    dashboard.keyword_var.set("data engineer")
                    self.assertTrue(dashboard._autosave_setup())
                    reloaded = load_or_create_config(paths)
                    self.assertEqual(reloaded.source.keyword, "data engineer")
                    self.assertEqual(dashboard.status_var.get(), "Settings saved.")
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_invalid_autosave_sets_status_and_keeps_existing_config(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                root = tk.Tk()
                root.withdraw()
                try:
                    dashboard = JobBotDashboard(root, config, paths, database)
                    original = load_or_create_config(paths).salary_floor
                    dashboard.salary_floor_var.set("not-a-number")
                    self.assertFalse(dashboard._autosave_setup())
                    reloaded = load_or_create_config(paths)
                    self.assertEqual(reloaded.salary_floor, original)
                    self.assertIn("Settings not saved:", dashboard.status_var.get())
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_strong_provider_sync_updates_model_and_persists(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                root = tk.Tk()
                root.withdraw()
                try:
                    dashboard = JobBotDashboard(root, config, paths, database)
                    dashboard.strong_stage_provider_var.set("openai")
                    dashboard._on_strong_provider_changed()
                    self.assertEqual(dashboard.strong_stage_model_var.get(), "gpt-5-mini")
                    self.assertTrue(dashboard._autosave_setup())
                    reloaded = load_or_create_config(paths)
                    self.assertEqual(reloaded.strong_stage_provider, "openai")
                    self.assertEqual(reloaded.strong_stage_model, "gpt-5-mini")
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_source_provider_and_jobspy_sites_persist(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                root = tk.Tk()
                root.withdraw()
                try:
                    dashboard = JobBotDashboard(root, config, paths, database)
                    dashboard.source_provider_var.set("jobspy")
                    dashboard.jobspy_sites_var.set("indeed, google")
                    self.assertTrue(dashboard._autosave_setup())
                    reloaded = load_or_create_config(paths)
                    self.assertEqual(reloaded.source.provider, "jobspy")
                    self.assertEqual(reloaded.source.jobspy_sites, ["indeed", "google"])
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_automation_mode_change_resets_results_per_page_default(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                root = tk.Tk()
                root.withdraw()
                try:
                    dashboard = JobBotDashboard(root, config, paths, database)
                    dashboard.automation_mode_var.set("auto")
                    dashboard._on_automation_mode_changed()
                    self.assertEqual(dashboard.results_per_page_var.get(), "25")
                    dashboard.automation_mode_var.set("semi_auto")
                    dashboard._on_automation_mode_changed()
                    self.assertEqual(dashboard.results_per_page_var.get(), "100")
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_fit_to_resume_applies_keywords_and_persists(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                root = tk.Tk()
                root.withdraw()
                try:
                    dashboard = JobBotDashboard(root, config, paths, database)
                    dashboard._apply_fit_to_resume_keywords("python developer automation llm")
                    reloaded = load_or_create_config(paths)
                    self.assertEqual(dashboard.keyword_var.get(), "python developer automation llm")
                    self.assertEqual(reloaded.source.keyword, "python developer automation llm")
                    self.assertEqual(dashboard.status_var.get(), "Resume-fit keywords generated. Review and edit them before running.")
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_document_status_text_reports_missing_and_not_generated(self) -> None:
        self.assertEqual(JobBotDashboard._document_status_text(""), "Not generated")
        self.assertIn("Generated but missing on disk:", JobBotDashboard._document_status_text("C:\\missing\\resume.pdf"))

    def test_doc_section_status_reports_yes_partial_and_no(self) -> None:
        self.assertEqual(JobBotDashboard._doc_section_status("accepted"), "Yes")
        self.assertEqual(JobBotDashboard._doc_section_status("partial"), "Partial")
        self.assertEqual(JobBotDashboard._doc_section_status("local"), "No")

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_generate_documents_updates_progress_and_reenables_button(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                database.upsert_job(
                    Job(
                        id="dash-gen-1",
                        title="Director of Ecommerce",
                        employer="MILK BAR",
                        location="New York, NY",
                        salary_range="",
                        description_full="Lead ecommerce growth and analytics.",
                        apply_method="board",
                        apply_url="https://example.com",
                        hiring_manager_email="",
                        source="jobspy",
                        posted_at="2026-01-01T00:00:00+00:00",
                        scraped_at="2026-01-01T00:00:00+00:00",
                    ),
                    {},
                )
                database.record_match_result(
                    "dash-gen-1",
                    score=82,
                    rationale="Strong fit",
                    strengths=[],
                    gaps=[],
                    is_match=True,
                    status="review",
                    error_message="",
                    scored_at="2026-01-01T00:00:00+00:00",
                )
                root = tk.Tk()
                root.withdraw()
                try:
                    dashboard = JobBotDashboard(root, config, paths, database)
                    dashboard.review_tree.selection_set("dash-gen-1")

                    class FakePipeline:
                        def __init__(self, db: Database, base: Path) -> None:
                            self.db = db
                            self.base = base

                        def generate_documents_for_job(self, job_id: str, *, progress_callback=None):
                            if progress_callback:
                                progress_callback("starting", "Starting document generation...", 0)
                                progress_callback("parsing_resume", "Loading and parsing resume...", 2)
                                progress_callback("validating_pages", "Validating final page count...", 5)
                                progress_callback("writing_cover_letter", "Writing cover letter...", 6)
                            target_dir = self.base / "output"
                            target_dir.mkdir(parents=True, exist_ok=True)
                            resume_pdf = target_dir / "resume.pdf"
                            cover = target_dir / "cover_letter.txt"
                            resume_pdf.write_text("pdf", encoding="utf-8")
                            cover.write_text("cover", encoding="utf-8")
                            self.db.record_generated_documents(
                                job_id,
                                output_dir=str(target_dir),
                                resume_docx_path="",
                                resume_pdf_path=str(resume_pdf),
                                cover_letter_path=str(cover),
                                status="generated",
                                error_message="",
                                generated_at="2026-04-07T16:52:00+00:00",
                            )
                            return GeneratedDocs(output_dir=target_dir, resume_pdf_path=resume_pdf, cover_letter_path=cover)

                    dashboard.pipeline = FakePipeline(database, Path(tmp))
                    dashboard._generate_documents_for_selected()
                    for _ in range(40):
                        root.update()
                        if not dashboard._generate_in_progress:
                            break
                        time.sleep(0.02)
                    self.assertFalse(dashboard._generate_in_progress)
                    self.assertEqual(str(dashboard.generate_button["state"]), "normal")
                    self.assertIn("Documents generated", dashboard.status_var.get())
                    self.assertEqual(dashboard.generate_progress_var.get(), 8)
                    row = database.get_review_row("dash-gen-1")
                    self.assertEqual(row["document_status"], "generated")
                    self.assertEqual(row["generated_at"], "2026-04-07T16:52:00+00:00")
                finally:
                    root.destroy()

    def test_refresh_review_queue_action_reloads_all_rows_and_updates_status(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                try:
                    database.upsert_job(
                        Job(
                            id="older-review-row",
                            title="Older Role",
                            employer="Example Co",
                            location="New York, NY, US",
                            salary_range="",
                            description_full="Older queued row",
                            apply_method="board",
                            apply_url="https://example.com/older",
                            hiring_manager_email="",
                            source="indeed",
                            posted_at="2026-04-01",
                            scraped_at="2026-04-01T12:00:00+00:00",
                        ),
                        {},
                    )
                    database.record_match_result(
                        "older-review-row",
                        score=70,
                        rationale="Queued for review",
                        strengths=[],
                        gaps=[],
                        is_match=True,
                        status="review",
                        error_message="",
                        scored_at="2026-04-01T12:05:00+00:00",
                    )
                    database.create_run("2026-04-07T20:00:00+00:00", stage="completed")

                    root = tk.Tk()
                    root.withdraw()
                    try:
                        dashboard = JobBotDashboard(root, config, paths, database)
                        dashboard._refresh_review_queue_action()
                        self.assertIn("older-review-row", dashboard.review_tree.get_children())
                        self.assertEqual(dashboard.status_var.get(), "Review Queue refreshed: 1 job loaded.")
                    finally:
                        root.destroy()
                finally:
                    database.close()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_doc_provider_change_syncs_doc_model_options(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                root = tk.Tk()
                root.withdraw()
                try:
                    dashboard = JobBotDashboard(root, config, paths, database)
                    dashboard.doc_stage_model_var.set("qwen2.5:7b")
                    dashboard.doc_stage_provider_var.set("openai")
                    dashboard._on_doc_provider_changed()
                    self.assertEqual(dashboard.doc_stage_model_var.get(), "gpt-5-mini")
                finally:
                    root.destroy()
