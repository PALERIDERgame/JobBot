from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from config import build_app_paths, load_or_create_config
from database import Database, Job
from match_scorer import MatchScore
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
                pipeline.scorer.score_job = lambda job, resume: MatchScore(
                    91, "Great fit", ["Python"], ["AWS"], True, "scored", "", "2026-01-01T00:00:00+00:00"
                )
                pipeline.gmail_client.deliver_match = lambda job, score, docs: type(
                    "Delivery",
                    (),
                    {"method": "local", "status": "skipped", "message_id": "", "error_message": ""},
                )()
                result = pipeline.run()
                self.assertEqual(result.status, "completed")
                rows = database.list_review_rows()
                self.assertEqual(len(rows), 1)
