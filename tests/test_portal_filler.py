from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from portal_filler import IndeedHandler, PortalFiller, detect_platform


class PortalFillerReadinessTests(unittest.TestCase):
    def test_check_readiness_reports_missing_playwright(self) -> None:
        with patch("portal_filler.importlib.import_module", side_effect=ImportError):
            readiness = PortalFiller.check_readiness()
        self.assertFalse(readiness.ready)
        self.assertEqual(readiness.reason_code, "missing_playwright")
        self.assertIn("ImportError", readiness.technical_detail)

    def test_check_readiness_reports_missing_browser_runtime(self) -> None:
        class FakeContextManager:
            def __enter__(self):
                chromium = types.SimpleNamespace(launch=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Executable doesn't exist")))
                return types.SimpleNamespace(chromium=chromium)

            def __exit__(self, exc_type, exc, tb):
                return False

        module = types.SimpleNamespace(sync_playwright=lambda: FakeContextManager())
        with patch("portal_filler.importlib.import_module", return_value=module):
            readiness = PortalFiller.check_readiness()
        self.assertFalse(readiness.ready)
        self.assertEqual(readiness.reason_code, "missing_browser_runtime")
        self.assertIn("browser_executable_launch_failed", readiness.technical_detail)

    def test_check_readiness_reports_access_denied_launch_detail(self) -> None:
        class FakeContextManager:
            def __enter__(self):
                chromium = types.SimpleNamespace(
                    launch=lambda **kwargs: (_ for _ in ()).throw(PermissionError("[WinError 5] Access is denied"))
                )
                return types.SimpleNamespace(chromium=chromium)

            def __exit__(self, exc_type, exc, tb):
                return False

        module = types.SimpleNamespace(sync_playwright=lambda: FakeContextManager())
        with patch("portal_filler.importlib.import_module", return_value=module):
            readiness = PortalFiller.check_readiness()
        self.assertFalse(readiness.ready)
        self.assertEqual(readiness.reason_code, "browser_launch_failed")
        self.assertIn("winerror_5_access_denied", readiness.technical_detail)

    def test_check_readiness_reports_ready(self) -> None:
        class FakeBrowser:
            def close(self):
                return None

        class FakeContextManager:
            def __enter__(self):
                chromium = types.SimpleNamespace(launch=lambda **kwargs: FakeBrowser())
                return types.SimpleNamespace(chromium=chromium)

            def __exit__(self, exc_type, exc, tb):
                return False

        module = types.SimpleNamespace(sync_playwright=lambda: FakeContextManager())
        with patch("portal_filler.importlib.import_module", return_value=module):
            readiness = PortalFiller.check_readiness()
        self.assertTrue(readiness.ready)
        self.assertEqual(readiness.reason_code, "ready")
        self.assertIn("launch succeeded", readiness.technical_detail.lower())


class PortalDetectionTests(unittest.TestCase):
    def test_detect_platform_returns_indeed_for_viewjob(self) -> None:
        self.assertEqual(detect_platform("https://www.indeed.com/viewjob?jk=123"), "indeed")

    def test_detect_platform_returns_indeed_for_apply_domain(self) -> None:
        self.assertEqual(detect_platform("https://apply.indeed.com/indeedapply/form/abc"), "indeed")


class IndeedHandlerTests(unittest.TestCase):
    def _build_handler(self, *, url: str, content: str = "", selectors: set[str] | None = None) -> IndeedHandler:
        selectors = selectors or set()

        class FakePage:
            def __init__(self) -> None:
                self.url = url

            def wait_for_load_state(self, *_args, **_kwargs):
                return None

            def content(self):
                return content

            def query_selector(self, selector):
                return object() if selector in selectors else None

        resume = types.SimpleNamespace(name="Jane Candidate", email="jane@example.com", phone="555-123-4567", header_lines=[])
        docs = types.SimpleNamespace(resume_pdf_path=None, resume_docx_path=None, cover_letter_path=None, output_dir=None)
        job = types.SimpleNamespace(title="Role", employer="Acme", apply_url=url)
        return IndeedHandler(FakePage(), resume, docs, job, None)

    def test_indeed_handler_marks_plain_viewjob_as_unsupported(self) -> None:
        handler = self._build_handler(url="https://www.indeed.com/viewjob?jk=123", content="job details")
        result = handler.fill()
        self.assertEqual(result.status, "unsupported")
        self.assertEqual(result.platform, "indeed")
        self.assertIn("posting page", result.message.lower())

    def test_indeed_handler_marks_screening_questions_for_manual_review(self) -> None:
        handler = self._build_handler(
            url="https://apply.indeed.com/indeedapply/form/abc",
            content="screening questions resume",
            selectors={"input[type='file']", "input[type='email']"},
        )
        result = handler.fill()
        self.assertEqual(result.status, "screening_questions")
        self.assertEqual(result.platform, "indeed")

    def test_indeed_handler_reports_login_wall(self) -> None:
        handler = self._build_handler(url="https://apply.indeed.com/indeedapply/form/abc", content="please sign in to apply")
        result = handler.fill()
        self.assertEqual(result.status, "login_required")
        self.assertEqual(result.platform, "indeed")
