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

    def test_parse_resume_prefers_summary_section_over_contact_block(self) -> None:
        with workspace_temp_dir() as tmp:
            resume_path = Path(tmp) / "resume.txt"
            cache_path = Path(tmp) / "resume_data.json"
            resume_path.write_text(
                "ROBERT THOM\nrobert@example.com | linkedin.com/in/example | (530) 220-4847\n"
                "PROFESSIONAL SUMMARY\nMarketing and operations leader with campaign, field, and analytics experience.\n"
                "KEY SKILLS\nDigital Advertising, Campaign Management, Operations\n"
                "WORK EXPERIENCE\nUnderdog Strategies - Digital Advertising and Field Manager\n",
                encoding="utf-8",
            )
            parsed = parse_resume(resume_path, cache_path)
            self.assertIn("Marketing and operations leader", parsed.summary)
            self.assertNotIn("linkedin.com", parsed.summary)
            self.assertIn("Digital Advertising", parsed.skills)

    def test_parse_resume_extracts_structured_sections(self) -> None:
        with workspace_temp_dir() as tmp:
            resume_path = Path(tmp) / "resume.txt"
            cache_path = Path(tmp) / "resume_data.json"
            resume_path.write_text(
                "ROBERT THOM\nrobert@example.com | linkedin.com/in/example | (530) 220-4847\n"
                "WORK EXPERIENCE\n"
                "Underdog Strategies, New York, NY — Digital Advertising and Field Manager\n"
                "JULY 2024 - Present\n"
                "● Led digital ad strategy and reporting.\n"
                "● Managed creative vendors and campaign launches.\n"
                "EDUCATION\n"
                "University of California, Davis\n"
                "Bachelor of Arts in Political Science Class of 2015\n"
                "KEY SKILLS\n"
                "Operations, Project Management, CRM, Data Analysis\n",
                encoding="utf-8",
            )
            parsed = parse_resume(resume_path, cache_path)
            self.assertEqual(parsed.header_lines[0], "ROBERT THOM")
            self.assertEqual(parsed.work_experience_entries[0].role_line, "Underdog Strategies, New York, NY — Digital Advertising and Field Manager")
            self.assertEqual(parsed.work_experience_entries[0].date_line, "JULY 2024 - Present")
            self.assertIn("University of California, Davis", parsed.education_lines)
            self.assertIn("Operations", " ".join(parsed.key_skills_lines))
