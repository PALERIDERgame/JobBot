from __future__ import annotations

import unittest
from pathlib import Path

from resume_parser import load_cached_resume, parse_resume
from test_support import workspace_temp_dir


class ResumeParserTests(unittest.TestCase):
    def test_parse_text_resume_and_cache(self) -> None:
        with workspace_temp_dir() as tmp:
            resume_path = Path(tmp) / "resume.txt"
            cache_path = Path(tmp) / "resume_data.json"
            resume_path.write_text(
                "Jane Candidate\njane@example.com\n555-123-4567\nSummary: Python engineer\nSkills: Python, SQL, APIs\nBuilt analytics platform\n",
                encoding="utf-8",
            )
            parsed = parse_resume(resume_path, cache_path)
            cached = load_cached_resume(cache_path)
            self.assertEqual(parsed.name, "Jane Candidate")
            self.assertIsNotNone(cached)
            self.assertIn("Python", parsed.skills)

    def test_parse_empty_resume_raises(self) -> None:
        with workspace_temp_dir() as tmp:
            resume_path = Path(tmp) / "resume.txt"
            cache_path = Path(tmp) / "resume_data.json"
            resume_path.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_resume(resume_path, cache_path)
