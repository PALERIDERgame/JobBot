from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from portal_filler import PortalFiller


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
