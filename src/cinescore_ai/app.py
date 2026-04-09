from __future__ import annotations

import sys

from cinescore_ai.audio import AudioWorkflowService
from cinescore_ai.config import AppConfigStore
from cinescore_ai.gemini import GeminiVideoAnalysisService
from cinescore_ai.gemini_music import GeminiMusicGenerationService
from cinescore_ai.localization import Localizer, detect_application_language
from cinescore_ai.paths import APP_NAME
from cinescore_ai.resolve import MockResolveAdapter, ResolveAdapter
from cinescore_ai.secrets import create_secret_store
from cinescore_ai.services import ConnectionTestService
from cinescore_ai.update_service import GitHubReleaseUpdateService
from cinescore_ai.ui.main_window import SettingsWindow
from cinescore_ai.workflow import ResolveWorkflowService

from PySide6.QtWidgets import QApplication


def launch_app(resolve_adapter: ResolveAdapter | None = None, block: bool = True) -> SettingsWindow:
    adapter = resolve_adapter or MockResolveAdapter()
    localizer = Localizer(detect_application_language())

    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication(sys.argv)

    assert app is not None
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    window = SettingsWindow(
        config_store=AppConfigStore(),
        secret_store=create_secret_store(),
        resolve_adapter=adapter,
        connection_test_service=ConnectionTestService(),
        gemini_video_analysis_service=GeminiVideoAnalysisService(),
        gemini_music_generation_service=GeminiMusicGenerationService(resolve_adapter=adapter),
        audio_workflow_service=AudioWorkflowService(resolve_adapter=adapter),
        resolve_workflow_service=ResolveWorkflowService(resolve_adapter=adapter),
        update_service=GitHubReleaseUpdateService(),
        localizer=localizer,
    )
    window.show()

    if owns_app and block:
        app.exec()

    return window
