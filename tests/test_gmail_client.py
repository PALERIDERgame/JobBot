from __future__ import annotations

import base64
import unittest
from pathlib import Path
from unittest.mock import MagicMock

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

    def test_employer_email_delivery_uses_job_email_without_fixed_recipient(self) -> None:
        with workspace_temp_dir() as tmp:
            resume_path = Path(tmp) / "resume.pdf"
            cover_letter_path = Path(tmp) / "cover_letter.txt"
            resume_path.write_bytes(b"resume")
            cover_letter_path.write_text("cover", encoding="utf-8")

            service = MagicMock()
            service.users.return_value.messages.return_value.send.return_value.execute.return_value = {"id": "msg-123"}
            client = GmailClient(
                GmailConfig(enabled=True, sender_email="me@example.com", recipient_email="", client_secrets_file="client.json"),
                Path(tmp) / "token.json",
            )
            client._build_service = lambda: service

            result = client.deliver_match(
                Job("1", "Engineer", "Acme", "Remote", "", "Email your resume to hiring@example.com", "email", "https://example.com", "hiring@example.com", "usajobs", "", ""),
                MatchScore(90, "Strong Python fit.", [], [], True, "scored", "", ""),
                GeneratedDocs(Path(tmp), resume_path, cover_letter_path),
            )

            self.assertEqual(result.status, "sent")
            self.assertEqual(result.method, "gmail_employer")
            send_kwargs = service.users.return_value.messages.return_value.send.call_args.kwargs
            raw_message = send_kwargs["body"]["raw"]
            decoded = base64.urlsafe_b64decode(raw_message.encode("utf-8")).decode("utf-8", errors="ignore")
            self.assertIn("To: hiring@example.com", decoded)
            self.assertIn("Subject: Application: Engineer at Acme", decoded)

    def test_board_delivery_without_fixed_recipient_fails_cleanly(self) -> None:
        with workspace_temp_dir() as tmp:
            resume_path = Path(tmp) / "resume.pdf"
            cover_letter_path = Path(tmp) / "cover_letter.txt"
            resume_path.write_bytes(b"resume")
            cover_letter_path.write_text("cover", encoding="utf-8")

            client = GmailClient(
                GmailConfig(enabled=True, sender_email="me@example.com", recipient_email="", client_secrets_file="client.json"),
                Path(tmp) / "token.json",
            )
            result = client.deliver_match(
                Job("1", "Engineer", "Acme", "Remote", "", "Role", "board", "https://example.com", "", "usajobs", "", ""),
                MatchScore(90, "Fit", [], [], True, "scored", "", ""),
                GeneratedDocs(Path(tmp), resume_path, cover_letter_path),
            )
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.error_message, "No delivery recipient available")
