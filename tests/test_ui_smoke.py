from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _path_setup import ensure_src_path

ensure_src_path()


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError:  # pragma: no cover - depends on local environment
    QApplication = None
    QMessageBox = None

from cinescore_ai.config import AppConfigStore
from cinescore_ai.audio import AudioWorkflowService
from cinescore_ai.gemini import GeminiVideoAnalysisService
from cinescore_ai.gemini_music import GeminiMusicGenerationService
from cinescore_ai.localization import Localizer
from cinescore_ai.providers import ConnectionTestResult
from cinescore_ai.resolve import MockResolveAdapter
from cinescore_ai.secrets import InMemorySecretStore
from cinescore_ai.services import ConnectionTestService
from cinescore_ai.workflow import ResolveWorkflowService

if QApplication is not None:
    from cinescore_ai.ui.main_window import SettingsWindow


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class SettingsWindowSmokeTests(unittest.TestCase):
    def test_settings_window_smoke(self) -> None:
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as temp_dir:
            adapter = MockResolveAdapter()
            window = SettingsWindow(
                config_store=AppConfigStore(config_file_path=Path(temp_dir) / "config.json"),
                secret_store=InMemorySecretStore(),
                resolve_adapter=adapter,
                connection_test_service=ConnectionTestService(session=None),
                gemini_video_analysis_service=GeminiVideoAnalysisService(session=None),
                gemini_music_generation_service=GeminiMusicGenerationService(resolve_adapter=adapter, session=None),
                audio_workflow_service=AudioWorkflowService(resolve_adapter=adapter, session=None),
                resolve_workflow_service=ResolveWorkflowService(resolve_adapter=adapter),
                localizer=Localizer("en"),
            )

            try:
                self.assertEqual(window.windowTitle(), "CineScore AI Settings")
                self.assertIn("Development Mode", window.runtime_label.text())
                self.assertTrue(window.version_label.text().startswith("Installed version: "))
                self.assertEqual(window.discord_button.text(), "")
                self.assertTrue(window.discord_button.isFlat())
                self.assertEqual(window.discord_button.width(), 44)
                self.assertEqual(window.discord_button.height(), 44)
                self.assertEqual(window.settings_tabs.count(), 5)
                self.assertEqual(window.settings_tabs.tabText(0), "Resolve")
                self.assertEqual(window.settings_tabs.tabText(1), "Gemini")
                self.assertEqual(window.settings_tabs.tabText(2), "Gemini Music")
                self.assertEqual(window.settings_tabs.tabText(3), "Audio")
                self.assertEqual(window.settings_tabs.tabText(4), "Paths")
                self.assertEqual(window.status_group.title(), "Status")
                self.assertFalse(window.save_button.isEnabled())
                self.assertEqual(window.project_name_label.text(), "Not loaded yet.")
                self.assertEqual(window.preview_render_label.text(), "No preview render queued.")
                self.assertEqual(window.preview_render_status_label.text(), "Idle")
                self.assertEqual(window.preview_render_progress_bar.value(), 0)
                self.assertEqual(window.gemini_analysis_source_label.text(), "No preview available yet.")
                self.assertEqual(window.gemini_analysis_preview.toPlainText(), "")
                self.assertEqual(window.gemini_music_source_label.text(), "No preview available yet.")
                self.assertEqual(window.gemini_music_preview.toPlainText(), "")
                self.assertEqual(window.audio_analysis_source_label.text(), "No Gemini plan available yet.")
                self.assertEqual(window.audio_generation_preview.toPlainText(), "")
            finally:
                window.close()

    def test_gemini_model_catalog_populates_combo_boxes(self) -> None:
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as temp_dir:
            adapter = MockResolveAdapter()
            window = SettingsWindow(
                config_store=AppConfigStore(config_file_path=Path(temp_dir) / "config.json"),
                secret_store=InMemorySecretStore(),
                resolve_adapter=adapter,
                connection_test_service=ConnectionTestService(session=None),
                gemini_video_analysis_service=GeminiVideoAnalysisService(session=None),
                gemini_music_generation_service=GeminiMusicGenerationService(resolve_adapter=adapter, session=None),
                audio_workflow_service=AudioWorkflowService(resolve_adapter=adapter, session=None),
                resolve_workflow_service=ResolveWorkflowService(resolve_adapter=adapter),
                localizer=Localizer("en"),
            )

            try:
                window._handle_gemini_result(
                    ConnectionTestResult(
                        ok=True,
                        message="Gemini connection succeeded.",
                        details={
                            "analysis_models": ["gemini-2.5-flash", "gemini-2.5-pro"],
                            "music_models": ["lyria-3-pro-preview", "lyria-3-clip-preview"],
                        },
                    )
                )

                self.assertEqual(window.gemini_model_edit.currentText(), "gemini-2.5-flash")
                self.assertEqual(window.gemini_music_model_combo.currentText(), "lyria-3-pro-preview")
                self.assertGreaterEqual(window.gemini_model_edit.count(), 2)
                self.assertGreaterEqual(window.gemini_music_model_combo.count(), 2)
            finally:
                window.close()

    def test_wav_error_detection_and_reason_classification_helpers(self) -> None:
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as temp_dir:
            adapter = MockResolveAdapter()
            window = SettingsWindow(
                config_store=AppConfigStore(config_file_path=Path(temp_dir) / "config.json"),
                secret_store=InMemorySecretStore(),
                resolve_adapter=adapter,
                connection_test_service=ConnectionTestService(session=None),
                gemini_video_analysis_service=GeminiVideoAnalysisService(session=None),
                gemini_music_generation_service=GeminiMusicGenerationService(resolve_adapter=adapter, session=None),
                audio_workflow_service=AudioWorkflowService(resolve_adapter=adapter, session=None),
                resolve_workflow_service=ResolveWorkflowService(resolve_adapter=adapter),
                localizer=Localizer("en"),
            )

            window._set_combo_value(window.gemini_music_output_combo, "wav")

            try:
                self.assertTrue(
                    window._should_offer_mp3_fallback(
                        "Cue 'A' requested WAV but Gemini returned audio/mpeg. Strict WAV mode rejected the response."
                    )
                )
                self.assertEqual(
                    window._classify_wav_error_reason(
                        "Cue 'A' requested WAV but Gemini returned audio/mpeg. Strict WAV mode rejected the response."
                    ),
                    "Error Y: Gemini returned non-WAV audio while WAV was requested.",
                )
                self.assertEqual(
                    window._classify_wav_error_reason(
                        "Gemini music generation failed (HTTP 400): generation_config.response_mime_type only allows text/plain"
                    ),
                    "Error X: Gemini rejected the WAV response MIME parameter.",
                )
            finally:
                window._set_dirty(False)
                window.close()

    def test_wav_error_detection_disabled_when_output_is_mp3(self) -> None:
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as temp_dir:
            adapter = MockResolveAdapter()
            window = SettingsWindow(
                config_store=AppConfigStore(config_file_path=Path(temp_dir) / "config.json"),
                secret_store=InMemorySecretStore(),
                resolve_adapter=adapter,
                connection_test_service=ConnectionTestService(session=None),
                gemini_video_analysis_service=GeminiVideoAnalysisService(session=None),
                gemini_music_generation_service=GeminiMusicGenerationService(resolve_adapter=adapter, session=None),
                audio_workflow_service=AudioWorkflowService(resolve_adapter=adapter, session=None),
                resolve_workflow_service=ResolveWorkflowService(resolve_adapter=adapter),
                localizer=Localizer("en"),
            )

            window._set_combo_value(window.gemini_music_output_combo, "mp3")

            try:
                self.assertFalse(
                    window._should_offer_mp3_fallback(
                        "Cue 'A' requested WAV but Gemini returned audio/mpeg. Strict WAV mode rejected the response."
                    )
                )
            finally:
                window._set_dirty(False)
                window.close()
