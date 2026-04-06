from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from config import build_app_paths, load_or_create_config
from database import Database
from test_support import workspace_temp_dir


class DashboardSmokeTests(unittest.TestCase):
    @unittest.skipIf(os.environ.get("CI") == "true", "Skipping Tk smoke test in CI")
    def test_dashboard_dependencies_initialize(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                database = Database(paths.database_file)
                database.initialize()
                self.assertEqual(config.source.provider, "usajobs")
