from __future__ import annotations

import unittest
from pathlib import Path

from database import Database, Job
from test_support import workspace_temp_dir


class DatabaseTests(unittest.TestCase):
    def test_initialize_and_upsert(self) -> None:
        with workspace_temp_dir() as tmp:
            db = Database(Path(tmp) / "jobbot.db")
            db.initialize()
            job = Job(
                id=Job.build_id("Acme", "Engineer", "Remote"),
                title="Engineer",
                employer="Acme",
                location="Remote",
                salary_range="",
                description_full="Build things",
                apply_method="board",
                apply_url="https://example.com",
                hiring_manager_email="",
                source="usajobs",
                posted_at="2026-01-01T00:00:00+00:00",
                scraped_at="2026-01-01T00:00:00+00:00",
            )
            db.upsert_job(job, {"sample": True})
            run_id = db.create_run("2026-01-01T00:00:00+00:00", "scraping")
            db.update_run(run_id, status="completed", jobs_seen=1, jobs_matched=0)
            rows = db.list_review_rows()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Engineer")
