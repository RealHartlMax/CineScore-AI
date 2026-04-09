from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.config import AppConfig, AppConfigStore


class AppConfigStoreTests(unittest.TestCase):
    def test_load_returns_defaults_when_file_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = AppConfigStore(config_file_path=Path(temp_dir) / "config.json")

            config = store.load()

            self.assertIsInstance(config, AppConfig)
            self.assertEqual(config.active_audio_provider, "aimlapi")
            self.assertEqual(config.gemini.model, "gemini-2.5-flash")

    def test_roundtrip_save_and_load(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            store = AppConfigStore(config_file_path=config_file)
            config = AppConfig()
            config.gemini.model = "gemini-1.5-flash"
            config.audio_provider.base_url = "https://example.invalid/v1"
            config.paths.output_directory = str(Path(temp_dir) / "output")
            config.paths.temp_preview_retention_days = 21

            store.save(config)

            reloaded = store.load()
            raw_payload = json.loads(config_file.read_text(encoding="utf-8"))

            self.assertEqual(reloaded.gemini.model, "gemini-1.5-flash")
            self.assertEqual(reloaded.audio_provider.base_url, "https://example.invalid/v1")
            self.assertEqual(raw_payload["paths"]["output_directory"], str(Path(temp_dir) / "output"))
            self.assertEqual(reloaded.paths.temp_preview_retention_days, 21)

    def test_invalid_json_falls_back_to_defaults(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text("{invalid", encoding="utf-8")
            store = AppConfigStore(config_file_path=config_file)

            config = store.load()

            self.assertTrue(config.gemini.endpoint.startswith("https://"))
