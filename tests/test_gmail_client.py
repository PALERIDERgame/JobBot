from __future__ import annotations

import unittest
from pathlib import Path

from config import GmailConfig
from database import Job
from doc_generator import GeneratedDocs
from gmail_client import GmailClient
from match_scorer import MatchScore
from test_support import workspace_temp_dir


class GmailClientTests(unittest.TestCase):
    def test_disabled_mode_skips_delivery(self) -> None:
        with workspace_temp_dir() as tmp:
            client = GmailClient(GmailConfig(enabled=False), Path(tmp) / "token.json")
            result = client.deliver_match(
                Job("1", "Engineer", "Acme", "Remote", "", "Role", "board", "https://example.com", "", "usajobs", "", ""),
                MatchScore(90, "Fit", [], [], True, "scored", "", ""),
                GeneratedDocs(Path(tmp), Path(tmp) / "resume.pdf", Path(tmp) / "cover_letter.txt"),
            )
            self.assertEqual(result.status, "skipped")
