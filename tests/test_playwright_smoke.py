from __future__ import annotations

import os
import unittest

from portal_filler import PortalFiller


@unittest.skipUnless(
    os.environ.get("JOBBOT_RUN_PLAYWRIGHT_SMOKE") == "1",
    "Set JOBBOT_RUN_PLAYWRIGHT_SMOKE=1 to run the real Playwright smoke test.",
)
class PlaywrightSmokeTests(unittest.TestCase):
    def test_real_playwright_runtime_is_ready(self) -> None:
        readiness = PortalFiller.check_readiness()
        self.assertTrue(
            readiness.ready,
            f"Expected Playwright runtime to be ready, got: {readiness.summary} ({readiness.technical_detail})",
        )
        self.assertEqual(readiness.reason_code, "ready")


if __name__ == "__main__":
    unittest.main()
