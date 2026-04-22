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
from gmail_client import DeliveryResult
from match_scorer import FitResumeSuggestions
from portal_filler import PortalAutofillReadiness
from test_support import workspace_temp_dir


class DashboardSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._portal_readiness_patcher = patch(
            "pipeline.PortalFiller.check_readiness",
            return_value=PortalAutofillReadiness(
                ready=False,
                summary="Portal autofill: unavailable (test stub)",
                reason_code="test_stub",
                technical_detail="",
            ),
        )
        self._portal_readiness_patcher.start()

    def tearDown(self) -> None:
        self._portal_readiness_patcher.stop()

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
    def test_fit_to_resume_applies_grouped_suggestions_and_persists(self) -> None:
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
                    dashboard._apply_fit_to_resume_suggestions(
                        FitResumeSuggestions(
                            combined_query="python developer automation llm",
                            core_titles=["python developer", "software engineer"],
                            adjacent_titles=["automation engineer", "platform engineer"],
                            domains=["developer tools"],
                            skills_tools=["python", "apis"],
                            broadening_terms=["workflow automation"],
                            rationale_by_term={"python developer": "Direct title evidence."},
                        )
                    )
                    reloaded = load_or_create_config(paths)
                    self.assertEqual(dashboard.keyword_var.get(), "python developer automation llm")
                    self.assertEqual(dashboard.target_titles_var.get(), "python developer, software engineer")
                    self.assertEqual(dashboard.include_titles_var.get(), "automation engineer, platform engineer")
                    self.assertEqual(reloaded.source.keyword, "python developer automation llm")
                    self.assertEqual(reloaded.target_titles, ["python developer", "software engineer"])
                    self.assertEqual(reloaded.include_titles, ["automation engineer", "platform engineer"])
                    self.assertEqual(dashboard.status_var.get(), "Resume-fit suggestions applied. Review and edit them before running.")
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
                            cover_txt = target_dir / "cover_letter.txt"
                            cover_docx = target_dir / "cover_letter.docx"
                            cover_pdf = target_dir / "cover_letter.pdf"
                            resume_pdf.write_text("pdf", encoding="utf-8")
                            cover_txt.write_text("cover", encoding="utf-8")
                            cover_docx.write_text("docx", encoding="utf-8")
                            cover_pdf.write_text("pdf", encoding="utf-8")
                            self.db.record_generated_documents(
                                job_id,
                                output_dir=str(target_dir),
                                resume_docx_path="",
                                resume_pdf_path=str(resume_pdf),
                                cover_letter_path=str(cover_txt),
                                cover_letter_docx_path=str(cover_docx),
                                cover_letter_pdf_path=str(cover_pdf),
                                status="generated",
                                error_message="",
                                generated_at="2026-04-07T16:52:00+00:00",
                            )
                            return GeneratedDocs(
                                output_dir=target_dir,
                                resume_pdf_path=resume_pdf,
                                cover_letter_pdf_path=cover_pdf,
                                cover_letter_docx_path=cover_docx,
                                cover_letter_txt_path=cover_txt,
                            )

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
    def test_review_queue_shows_hr_email_presence_column(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                try:
                    database.upsert_job(
                        Job(
                            id="email-present-row",
                            title="Head of Marketing",
                            employer="Acme",
                            location="New York, NY, US",
                            salary_range="",
                            description_full="Lead marketing.",
                            apply_method="email",
                            apply_url="https://example.com",
                            hiring_manager_email="talent@example.com",
                            source="indeed",
                            posted_at="2026-04-08",
                            scraped_at="2026-04-08T00:00:00+00:00",
                        ),
                        {},
                    )
                    database.record_match_result(
                        "email-present-row",
                        score=0,
                        rationale="Queued",
                        strengths=[],
                        gaps=[],
                        is_match=False,
                        status="review",
                        error_message="",
                        scored_at="2026-04-08T00:00:00+00:00",
                    )
                    root = tk.Tk()
                    root.withdraw()
                    try:
                        dashboard = JobBotDashboard(root, config, paths, database)
                        values = dashboard.review_tree.item("email-present-row", "values")
                        self.assertEqual(values[6], "present")
                    finally:
                        root.destroy()
                finally:
                    database.close()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_review_details_show_not_present_hr_email(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                try:
                    database.upsert_job(
                        Job(
                            id="email-risk-row",
                            title="VP Communications",
                            employer="Acme",
                            location="New York, NY, US",
                            salary_range="",
                            description_full=(
                                "For privacy questions, contact compliance@acme.com.\n"
                                "This inbox is not monitored for application status updates."
                            ),
                            apply_method="email",
                            apply_url="https://example.com/job",
                            hiring_manager_email="compliance@acme.com",
                            source="indeed",
                            posted_at="2026-04-01",
                            scraped_at="2026-04-01T12:00:00+00:00",
                        ),
                        {},
                    )
                    database.record_match_result(
                        "email-risk-row",
                        score=70,
                        rationale="Queued for review",
                        strengths=[],
                        gaps=[],
                        is_match=True,
                        status="review",
                        error_message="",
                        scored_at="2026-04-01T12:05:00+00:00",
                    )
                    root = tk.Tk()
                    root.withdraw()
                    try:
                        dashboard = JobBotDashboard(root, config, paths, database)
                        dashboard.review_tree.selection_set("email-risk-row")
                        dashboard._refresh_selected_details()
                        details = dashboard.details_text.get("1.0", tk.END)
                        self.assertIn("HR email: not present", details)
                        self.assertIn("HR email review: No validated HR/application email was found in the posting.", details)
                        heading, body, button = dashboard._approve_and_send_confirmation_copy(database.get_review_row("email-risk-row"))
                        self.assertIn("blocked", heading.lower())
                        self.assertIn("will not send", body.lower())
                        self.assertEqual(button, "Continue")
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

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_dashboard_shows_portal_readiness_on_init(self) -> None:
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
                    dashboard.pipeline.portal_autofill_readiness = lambda: type(
                        "Readiness",
                        (),
                        {"ready": False, "summary": "Portal autofill: unavailable (Playwright not installed)", "reason_code": "missing_playwright"},
                    )()
                    dashboard._refresh_portal_readiness()
                    self.assertEqual(dashboard.portal_readiness_var.get(), "Portal autofill: unavailable (Playwright not installed)")
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_dashboard_refresh_updates_portal_readiness(self) -> None:
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
                    dashboard.pipeline.portal_autofill_readiness = lambda: type(
                        "Readiness",
                        (),
                        {"ready": True, "summary": "Portal autofill: ready", "reason_code": "ready"},
                    )()
                    dashboard.refresh_view()
                    self.assertEqual(dashboard.portal_readiness_var.get(), "Portal autofill: ready")
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_dashboard_shows_gmail_readiness(self) -> None:
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
                    dashboard.pipeline.gmail_client.readiness_status = lambda: (
                        False,
                        "Gmail send readiness: authentication required",
                    )
                    dashboard._refresh_gmail_readiness()
                    self.assertEqual(
                        dashboard.gmail_readiness_var.get(),
                        "Gmail send readiness: authentication required",
                    )
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_approve_and_send_confirmation_copy_for_email_job(self) -> None:
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
                    heading, detail, action = dashboard._approve_and_send_confirmation_copy(
                        {
                            "title": "Head of Marketing",
                            "employer": "Acme",
                            "apply_method": "email",
                            "apply_url": "https://example.com/job",
                            "description_full": "Please send your resume and cover letter to talent@example.com to apply.",
                            "hiring_manager_email": "talent@example.com",
                        }
                    )
                    self.assertIn("send an application email", heading.lower())
                    self.assertIn("talent@example.com", detail)
                    self.assertEqual(action, "Send application")
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_approve_and_send_cancel_sets_status_and_does_not_start_thread(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                database.upsert_job(
                    Job(
                        id="approve-confirm-row",
                        title="Head of Marketing",
                        employer="Acme",
                        location="New York, NY, US",
                        salary_range="",
                        description_full="Lead marketing.",
                        apply_method="board",
                        apply_url="https://example.com",
                        hiring_manager_email="",
                        source="indeed",
                        posted_at="2026-04-08",
                        scraped_at="2026-04-08T00:00:00+00:00",
                    ),
                    {},
                )
                database.record_match_result(
                    "approve-confirm-row",
                    score=0,
                    rationale="Queued",
                    strengths=[],
                    gaps=[],
                    is_match=False,
                    status="review",
                    error_message="",
                    scored_at="2026-04-08T00:00:00+00:00",
                )
                root = tk.Tk()
                root.withdraw()
                try:
                    dashboard = JobBotDashboard(root, config, paths, database)
                    dashboard.review_tree.selection_set("approve-confirm-row")
                    with patch.object(dashboard, "_confirm_approve_and_send", return_value=False):
                        with patch("dashboard.threading.Thread") as thread_mock:
                            dashboard._approve_and_send()
                    self.assertEqual(dashboard.status_var.get(), "Approve and Send canceled.")
                    thread_mock.assert_not_called()
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_approve_and_send_background_reports_manual_apply_status(self) -> None:
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

                    class FakePipeline:
                        def approve_and_send(self, job_id: str, *, progress_callback=None):
                            if progress_callback:
                                progress_callback("attempting_portal", "Attempting portal autofill...", 6)
                            return DeliveryResult(
                                "greenhouse",
                                "blocked_login",
                                "",
                                "Login wall blocked autofill; apply page opened for manual completion.",
                            )

                    dashboard.pipeline = FakePipeline()
                    dashboard._approve_and_send_background("job-1")
                    root.update()
                    self.assertIn("blocked_login via greenhouse", dashboard.status_var.get())
                    self.assertIn("opened for manual completion", dashboard.status_var.get())
                finally:
                    root.destroy()

    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_test_portal_runtime_uses_shared_progress_ui(self) -> None:
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

                    class FakePipeline:
                        def __init__(self) -> None:
                            self.portal_readiness = type(
                                "Readiness",
                                (),
                                {
                                    "ready": False,
                                    "summary": "Portal autofill: unavailable (Chromium launch failed)",
                                    "reason_code": "browser_launch_failed",
                                    "technical_detail": "winerror_5_access_denied: PermissionError: [WinError 5] Access is denied",
                                },
                            )()

                        def verify_portal_autofill_runtime(self, *, progress_callback=None):
                            if progress_callback:
                                progress_callback("starting", "Testing portal autofill runtime...", 0)
                                progress_callback("checking_runtime", "Importing Playwright and launching headless Chromium...", 4)
                                progress_callback(
                                    "runtime_checked",
                                    "Portal autofill: unavailable (Chromium launch failed) - winerror_5_access_denied: PermissionError: [WinError 5] Access is denied",
                                    7,
                                )
                            return self.portal_readiness

                    dashboard.pipeline = FakePipeline()
                    dashboard._test_portal_autofill_runtime()
                    for _ in range(40):
                        root.update()
                        if not dashboard._generate_in_progress:
                            break
                        time.sleep(0.02)
                    self.assertFalse(dashboard._generate_in_progress)
                    self.assertEqual(dashboard.generate_progress_var.get(), 8)
                    self.assertEqual(
                        dashboard.generate_context_var.get(),
                        "Portal autofill runtime verification",
                    )
                    self.assertIn("Chromium launch failed", dashboard.status_var.get())
                    self.assertEqual(
                        dashboard.portal_readiness_var.get(),
                        "Portal autofill: unavailable (Chromium launch failed)",
                    )
                finally:
                    root.destroy()
