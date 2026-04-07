from __future__ import annotations

from datetime import date
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

    def test_upsert_job_serializes_non_json_native_payload_values(self) -> None:
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
                source="jobspy",
                posted_at="2026-01-01T00:00:00+00:00",
                scraped_at="2026-01-01T00:00:00+00:00",
            )
            db.upsert_job(job, {"posted_date": date(2026, 1, 1)})
            rows = db.list_review_rows()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Engineer")

    def test_list_review_rows_can_filter_to_latest_run_window(self) -> None:
        with workspace_temp_dir() as tmp:
            db = Database(Path(tmp) / "jobbot.db")
            db.initialize()
            older = Job(
                id=Job.build_id("Acme", "Engineer", "Remote"),
                title="Engineer",
                employer="Acme",
                location="Remote",
                salary_range="",
                description_full="Build things",
                apply_method="board",
                apply_url="https://example.com",
                hiring_manager_email="",
                source="jobspy",
                posted_at="2026-01-01T00:00:00+00:00",
                scraped_at="2026-01-01T00:00:00+00:00",
            )
            newer = Job(
                id=Job.build_id("Beta", "Analyst", "Remote"),
                title="Analyst",
                employer="Beta",
                location="Remote",
                salary_range="",
                description_full="Analyze things",
                apply_method="board",
                apply_url="https://example.com/2",
                hiring_manager_email="",
                source="jobspy",
                posted_at="2026-01-02T00:00:00+00:00",
                scraped_at="2026-01-02T12:00:00+00:00",
            )
            db.upsert_job(older, {"sample": True})
            db.upsert_job(newer, {"sample": True})
            rows = db.list_review_rows(min_scraped_at="2026-01-02T00:00:00+00:00")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Analyst")
