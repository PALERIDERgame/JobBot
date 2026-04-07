from __future__ import annotations

import os
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from config import build_app_paths, load_or_create_config
from database import Database
from dashboard import JobBotDashboard
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
