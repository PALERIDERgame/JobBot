from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from config import build_app_paths, load_or_create_config, resolve_output_dir, save_config
from test_support import workspace_temp_dir


class ConfigTests(unittest.TestCase):
    def test_load_or_create_config_creates_defaults(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                self.assertTrue(paths.config_file.exists())
                self.assertEqual(config.scoring_threshold, 70)
                self.assertEqual(config.source.results_per_page, 100)
                self.assertEqual(config.cheap_stage_provider, "ollama_local")
                self.assertEqual(config.strong_stage_provider, "anthropic")

    def test_resolve_output_dir_uses_appdata_when_relative(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                output_dir = resolve_output_dir(config, paths)
                self.assertEqual(output_dir, paths.root / "output")

    def test_save_config_round_trip(self) -> None:
        with workspace_temp_dir() as tmp:
            with patch.dict(os.environ, {"APPDATA": str(tmp)}):
                paths = build_app_paths()
                config = load_or_create_config(paths)
                config.source.keyword = "data engineer"
                save_config(config, paths.config_file)
                loaded = load_or_create_config(paths)
                self.assertEqual(loaded.source.keyword, "data engineer")
