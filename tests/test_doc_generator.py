from __future__ import annotations

import unittest
from pathlib import Path

from database import Job
from doc_generator import DocumentGenerator
from match_scorer import MatchScore
from resume_parser import ResumeData
from test_support import workspace_temp_dir


class DocumentGeneratorTests(unittest.TestCase):
    def test_generate_creates_files(self) -> None:
        with workspace_temp_dir() as tmp:
            generator = DocumentGenerator()
            docs = generator.generate(
                Path(tmp),
                Job("1", "Engineer", "Acme", "Remote", "", "Role", "board", "https://example.com", "", "usajobs", "", ""),
                ResumeData("", "", "Jane", "jane@example.com", "555", "Summary", ["Python"], ["Built APIs"]),
                MatchScore(90, "Great fit", ["Python"], ["AWS"], True, "scored", "", "2026-01-01T00:00:00+00:00"),
            )
            self.assertTrue(docs.resume_pdf_path.exists())
            self.assertTrue(docs.cover_letter_path.exists())
