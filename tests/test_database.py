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
            latest_run = db.latest_run()
            self.assertIsNotNone(latest_run)
            assert latest_run is not None
            self.assertEqual(latest_run["status"], "completed")

    def test_latest_run_returns_structured_runs_metrics(self) -> None:
        with workspace_temp_dir() as tmp:
            db = Database(Path(tmp) / "jobbot.db")
            db.initialize()
            run_id = db.create_run("2026-01-01T00:00:00+00:00", "fast_ranking")
            db.update_run(
                run_id,
                status="completed",
                jobs_seen=12,
                jobs_matched=3,
                estimated_cost_usd=0.1234,
                fast_rank_candidates=12,
                fast_rank_survivors=7,
                cheap_shortlist_size=5,
                cheap_stage_duration_ms=2300,
                cheap_stage_provider="openai",
                cheap_stage_model="gpt-5-nano",
                cheap_parse_failures=1,
                strong_shortlist_size=2,
                strong_stage_duration_ms=900,
                strong_stage_provider="openai",
                strong_stage_model="gpt-5-mini",
                strong_parse_failures=0,
                error_summary="",
            )
            latest_run = db.latest_run()
            self.assertIsNotNone(latest_run)
            assert latest_run is not None
            self.assertEqual(latest_run["fast_rank_candidates"], 12)
            self.assertEqual(latest_run["fast_rank_survivors"], 7)
            self.assertEqual(latest_run["cheap_shortlist_size"], 5)
            self.assertEqual(latest_run["cheap_stage_provider"], "openai")
            self.assertEqual(latest_run["cheap_parse_failures"], 1)
            self.assertEqual(latest_run["strong_shortlist_size"], 2)
            self.assertEqual(latest_run["strong_stage_model"], "gpt-5-mini")

    def test_recent_runs_returns_descending_rows(self) -> None:
        with workspace_temp_dir() as tmp:
            db = Database(Path(tmp) / "jobbot.db")
            db.initialize()
            first = db.create_run("2026-01-01T00:00:00+00:00", "scraping")
            second = db.create_run("2026-01-02T00:00:00+00:00", "cheap_scoring")
            db.update_run(first, status="completed")
            db.update_run(second, status="completed", cheap_parse_failures=2)
            rows = db.recent_runs(limit=2)
            self.assertEqual([row["id"] for row in rows], [second, first])
            self.assertEqual(rows[0]["cheap_parse_failures"], 2)

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
