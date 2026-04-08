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

    # Location and salary checks were removed from the deterministic filter.
    # They are now handled by the cheap AI stage (Ollama) via screening_constraints
    # in match_scorer._build_cheap_prompt(), allowing for more nuanced decisions.
