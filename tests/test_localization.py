from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.localization import Localizer, detect_application_language, read_resolve_language_code


class LocalizationTests(unittest.TestCase):
    def test_detect_application_language_reads_resolve_preference_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            preferences_file = Path(temp_dir) / "config.user.xml"
            preferences_file.write_text(
                "<?xml version='1.0' encoding='UTF-8'?><SM_UserPrefs><Language>de_DE</Language></SM_UserPrefs>",
                encoding="utf-8",
            )

            self.assertEqual(read_resolve_language_code(preferences_file), "de_DE")
            self.assertEqual(detect_application_language(preferences_file), "de")

    def test_localizer_falls_back_to_english_for_unknown_language(self) -> None:
        localizer = Localizer("fr_FR")

        self.assertEqual(localizer.language_code, "en")
        self.assertEqual(localizer.t("Save"), "Save")

    def test_localizer_returns_german_translation_when_available(self) -> None:
        localizer = Localizer("de_DE")

        self.assertEqual(localizer.t("Save"), "Speichern")
        self.assertEqual(localizer.t("No preview available yet."), "Noch keine Vorschau verfügbar.")
