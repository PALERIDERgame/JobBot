from __future__ import annotations

import unittest

from config import JobBotConfig
from database import Job
from deterministic_filter import apply_deterministic_filter


class DeterministicFilterTests(unittest.TestCase):
    def test_filters_excluded_titles(self) -> None:
        config = JobBotConfig()
        job = Job("1", "Principal Engineer", "Acme", "Remote", "", "Role", "board", "https://example.com", "", "usajobs", "", "")
        result = apply_deterministic_filter(job, config, seen_job_ids=set())
        self.assertEqual(result.outcome, "filtered_out")

    def test_force_escalate_keyword_marks_job(self) -> None:
        config = JobBotConfig(force_escalate_keywords=["agentic"])
        job = Job("1", "Software Engineer", "Acme", "Remote", "", "Agentic workflow platform", "board", "https://example.com", "", "usajobs", "", "")
        result = apply_deterministic_filter(job, config, seen_job_ids=set())
        self.assertEqual(result.outcome, "force_escalate")

    def test_location_matches_nyc_boroughs(self) -> None:
        config = JobBotConfig()
        config.source.location = "New York, NY"
        job = Job("1", "Software Engineer", "Acme", "Brooklyn, NY, US", "", "Role", "board", "https://example.com", "", "jobspy", "", "")
        result = apply_deterministic_filter(job, config, seen_job_ids=set())
        self.assertNotEqual(result.outcome, "filtered_out")

    def test_location_rejects_nearby_non_matching_state(self) -> None:
        config = JobBotConfig()
        config.source.location = "New York, NY"
        job = Job("1", "Software Engineer", "Acme", "Denville, NJ, US", "", "Role", "board", "https://example.com", "", "jobspy", "", "")
        result = apply_deterministic_filter(job, config, seen_job_ids=set())
        self.assertEqual(result.outcome, "filtered_out")

    def test_location_allows_remote_jobs(self) -> None:
        config = JobBotConfig()
        config.source.location = "New York, NY"
        job = Job("1", "Software Engineer", "Acme", "Remote", "", "Role", "board", "https://example.com", "", "jobspy", "", "")
        result = apply_deterministic_filter(job, config, seen_job_ids=set())
        self.assertNotEqual(result.outcome, "filtered_out")

    def test_salary_floor_allows_hourly_full_time_when_annualized(self) -> None:
        config = JobBotConfig()
        config.salary_floor = 80000
        job = Job("1", "Software Engineer", "Acme", "Remote", "$45/hour", "Role", "board", "https://example.com", "", "jobspy", "", "")
        result = apply_deterministic_filter(job, config, seen_job_ids=set())
        self.assertNotEqual(result.outcome, "filtered_out")

    def test_salary_floor_rejects_low_monthly_when_annualized(self) -> None:
        config = JobBotConfig()
        config.salary_floor = 80000
        job = Job("1", "Software Engineer", "Acme", "Remote", "$4,000/month", "Role", "board", "https://example.com", "", "jobspy", "", "")
        result = apply_deterministic_filter(job, config, seen_job_ids=set())
        self.assertEqual(result.outcome, "filtered_out")

    def test_salary_floor_skips_part_time_compensation(self) -> None:
        config = JobBotConfig()
        config.salary_floor = 80000
        job = Job("1", "Software Engineer", "Acme", "Remote", "$40/hour part-time", "Role", "board", "https://example.com", "", "jobspy", "", "")
        result = apply_deterministic_filter(job, config, seen_job_ids=set())
        self.assertNotEqual(result.outcome, "filtered_out")
