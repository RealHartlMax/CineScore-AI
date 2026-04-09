from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from cinescore_ai.audio import AudioCompositionResult, AudioGenerationProgressUpdate, AudioWorkflowService
from cinescore_ai.config import (
    AppConfig,
    AppConfigStore,
    AudioProviderSettings,
    GeminiMusicSettings,
    GeminiSettings,
    get_default_audio_provider_settings,
)
from cinescore_ai.gemini import GeminiAnalysisProgressUpdate, GeminiVideoAnalysisResult, GeminiVideoAnalysisService
from cinescore_ai.gemini_music import (
    GeminiMusicGenerationResult,
    GeminiMusicGenerationService,
    GeminiMusicProgressUpdate,
)
from cinescore_ai.localization import Localizer
from cinescore_ai.providers import ConnectionTestResult
from cinescore_ai.resolve import PreviewRenderJob, ResolveAdapter, ResolveTimelineContext
from cinescore_ai.secrets import GEMINI_API_KEY_SECRET, SecretStore, get_audio_provider_secret_name
from cinescore_ai.services import ConnectionTestService
from cinescore_ai.update_service import GitHubReleaseUpdateService, ReleaseInfo, UpdateCheckResult
from cinescore_ai.ui.workers import BackgroundTask
from cinescore_ai.version import get_app_version
from cinescore_ai.workflow import PreviewRenderExecutionResult, PreviewRenderProgressUpdate, ResolveWorkflowService


class UpdateAvailableDialog(QDialog):
    def __init__(
        self,
        *,
        parent: QWidget,
        current_version: str,
        release: ReleaseInfo,
        newer_releases: tuple[ReleaseInfo, ...],
        translate,
        can_self_update: bool,
    ) -> None:
        super().__init__(parent)
        self._release = release
        self._newer_releases = newer_releases
        self._translate = translate
        self.setWindowTitle(translate("Update available"))
        self.resize(720, 480)

        layout = QVBoxLayout(self)
        summary_label = QLabel(translate("A new CineScore AI version is available."))
        summary_label.setWordWrap(True)

        details_label = QLabel(
            "\n".join(
                [
                    translate("Installed version: {version}", version=current_version),
                    translate("Latest version: {version}", version=release.version),
                    translate("Release: {title}", title=release.title),
                ]
            )
        )
        details_label.setWordWrap(True)

        notes_label = QLabel(translate("Release notes"))
        notes_label.setStyleSheet("font-weight: 600;")

        notes_view = QPlainTextEdit()
        notes_view.setReadOnly(True)
        notes_view.setPlainText(self._build_release_notes())

        button_box = QDialogButtonBox()
        self.update_button = button_box.addButton(
            translate("Update now"),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.update_button.setEnabled(can_self_update)
        self.later_button = button_box.addButton(
            translate("Later"),
            QDialogButtonBox.ButtonRole.RejectRole,
        )

        self.update_button.clicked.connect(self.accept)
        self.later_button.clicked.connect(self.reject)

        layout.addWidget(summary_label)
        layout.addWidget(details_label)
        layout.addWidget(notes_label)
        layout.addWidget(notes_view, 1)
        layout.addWidget(button_box)

    def _build_release_notes(self) -> str:
        releases = self._newer_releases or ((self._release,) if self._release else ())
        sections: list[str] = []
        for release in releases:
            body = (release.body or "").strip()
            if not body:
                continue
            title = release.title.strip() or f"v{release.version}"
            sections.append(f"===== {title} =====\n{body}")
        if sections:
            return "\n\n".join(sections)
        return self._translate("No changelog provided for this release.")

        if not can_self_update:
            hint_label = QLabel(translate("Automatic update is currently only supported on Windows."))
            hint_label.setWordWrap(True)
            hint_label.setStyleSheet("color: #c58b36;")
            layout.insertWidget(3, hint_label)

    @property
    def release(self) -> ReleaseInfo:
        return self._release


class SettingsWindow(QMainWindow):
    DISCORD_INVITE_URL = "https://discord.gg/ZhuhFhZrM5"

    def __init__(
        self,
        config_store: AppConfigStore,
        secret_store: SecretStore,
        resolve_adapter: ResolveAdapter,
        connection_test_service: ConnectionTestService,
        gemini_video_analysis_service: GeminiVideoAnalysisService,
        gemini_music_generation_service: GeminiMusicGenerationService,
        audio_workflow_service: AudioWorkflowService,
        resolve_workflow_service: ResolveWorkflowService,
        update_service: GitHubReleaseUpdateService | None = None,
        localizer: Localizer | None = None,
    ) -> None:
        super().__init__()
        self._config_store = config_store
        self._secret_store = secret_store
        self._resolve_adapter = resolve_adapter
        self._connection_test_service = connection_test_service
        self._gemini_video_analysis_service = gemini_video_analysis_service
        self._gemini_music_generation_service = gemini_music_generation_service
        self._audio_workflow_service = audio_workflow_service
        self._resolve_workflow_service = resolve_workflow_service
        self._update_service = update_service
        self._localizer = localizer or Localizer("en")
        self._thread_pool = QThreadPool.globalInstance()
        self._active_workers: set[BackgroundTask] = set()
        self._is_loading_form = False
        self._dirty = False
        self._loaded_config = self._config_store.load()
        self._current_context: ResolveTimelineContext | None = None
        self._last_preview_render: PreviewRenderJob | None = None
        self._last_gemini_analysis_result: GeminiVideoAnalysisResult | None = None
        self._last_gemini_music_result: GeminiMusicGenerationResult | None = None
        self._last_audio_composition_result: AudioCompositionResult | None = None
        self._last_preview_progress_message = ""
        self._last_gemini_progress_message = ""
        self._last_gemini_music_progress_message = ""
        self._last_audio_progress_message = ""
        self._update_check_in_progress = False
        self._update_dialog_shown = False

        self._build_ui()
        self._populate_form(self._loaded_config)
        self._apply_runtime_state()
        if self._update_service is not None:
            QTimer.singleShot(250, self._check_for_updates_silently)

    def _build_ui(self) -> None:
        self.setWindowTitle(self._t("CineScore AI Settings"))
        self.setMinimumSize(860, 680)

        central_widget = QWidget(self)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        self.runtime_label = QLabel()
        self.runtime_label.setWordWrap(True)
        self.runtime_label.setStyleSheet("font-weight: 600;")

        self.version_label = QLabel()
        self.version_label.setWordWrap(True)

        self.secret_backend_label = QLabel()
        self.secret_backend_label.setWordWrap(True)

        self.discord_button = QPushButton(self._t("Discord"))
        self.discord_button.setObjectName("discordButton")
        self.discord_button.setText("")
        self.discord_button.setFlat(True)
        self.discord_button.setFixedSize(44, 44)
        self.discord_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.discord_button.setToolTip(self._t("Open the CineScore AI Discord community."))
        self.discord_button.setIconSize(QSize(28, 28))
        self._discord_icon_default = QIcon()
        self._discord_icon_hover = QIcon()
        discord_assets_dir = Path(__file__).resolve().parent / "assets"
        discord_icon_default_path = discord_assets_dir / "discord.svg"
        discord_icon_hover_path = discord_assets_dir / "discord_hover.svg"
        if discord_icon_default_path.exists():
            self._discord_icon_default = QIcon(str(discord_icon_default_path))
        if discord_icon_hover_path.exists():
            self._discord_icon_hover = QIcon(str(discord_icon_hover_path))
        self._set_discord_button_icon(hovered=False)
        self.discord_button.installEventFilter(self)
        self.discord_button.clicked.connect(self._open_discord_community)

        self.settings_tabs = QTabWidget()
        self.settings_tabs.setDocumentMode(True)
        self.settings_tabs.addTab(self._build_tab_page(self._build_resolve_group()), self._t("Resolve"))
        self.settings_tabs.addTab(self._build_tab_page(self._build_gemini_group()), self._t("Gemini"))
        self.settings_tabs.addTab(self._build_tab_page(self._build_gemini_music_group()), self._t("Gemini Music"))
        self.settings_tabs.addTab(self._build_tab_page(self._build_audio_group()), self._t("Audio"))
        self.settings_tabs.addTab(self._build_tab_page(self._build_paths_group()), self._t("Paths"))

        self.status_group = self._build_status_group()

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.addStretch(1)

        self.discard_button = QPushButton(self._t("Discard unsaved changes"))
        self.discard_button.clicked.connect(self._discard_changes)

        self.test_gemini_button = QPushButton(self._t("Test Gemini"))
        self.test_gemini_button.clicked.connect(self._test_gemini_connection)

        self.test_audio_button = QPushButton(self._t("Test Audio Provider"))
        self.test_audio_button.clicked.connect(self._test_audio_connection)

        self.check_updates_button = QPushButton(self._t("Check for updates"))
        self.check_updates_button.clicked.connect(self._check_for_updates_manually)
        self.check_updates_button.setEnabled(self._update_service is not None)

        self.save_button = QPushButton(self._t("Save"))
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save_settings)

        buttons_layout.addWidget(self.discard_button)
        buttons_layout.addWidget(self.test_gemini_button)
        buttons_layout.addWidget(self.test_audio_button)
        buttons_layout.addWidget(self.check_updates_button)
        buttons_layout.addWidget(self.save_button)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(4)
        header_text_layout.addWidget(self.runtime_label)
        header_text_layout.addWidget(self.version_label)
        header_text_layout.addWidget(self.secret_backend_label)

        header_layout.addLayout(header_text_layout, 1)
        header_layout.addWidget(self.discord_button, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        root_layout.addLayout(header_layout)
        root_layout.addWidget(self.settings_tabs, 1)
        root_layout.addWidget(self.status_group)
        root_layout.addLayout(buttons_layout)

        self.setCentralWidget(central_widget)
        self._apply_resolve_theme()

    def _build_tab_page(self, *sections: QWidget) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        for section in sections:
            content_layout.addWidget(section)
        content_layout.addStretch(1)

        scroll_area.setWidget(content)
        page_layout.addWidget(scroll_area)
        return page

    def _build_resolve_group(self) -> QGroupBox:
        group = QGroupBox(self._t("Resolve Context"))
        outer_layout = QVBoxLayout(group)
        outer_layout.setSpacing(10)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.project_name_label = QLabel(self._t("Not loaded yet."))
        self.project_name_label.setWordWrap(True)
        self.timeline_name_label = QLabel(self._t("Not loaded yet."))
        self.timeline_name_label.setWordWrap(True)
        self.timeline_start_label = QLabel(self._t("Not loaded yet."))
        self.timeline_start_label.setWordWrap(True)
        self.timeline_frame_rate_label = QLabel(self._t("Not loaded yet."))
        self.timeline_frame_rate_label.setWordWrap(True)
        self.timeline_marker_count_label = QLabel(self._t("Not loaded yet."))
        self.timeline_marker_count_label.setWordWrap(True)
        self.preview_render_label = QLabel(self._t("No preview render queued."))
        self.preview_render_label.setWordWrap(True)
        self.preview_render_status_label = QLabel(self._t("Idle"))
        self.preview_render_status_label.setWordWrap(True)
        self.preview_render_progress_bar = QProgressBar()
        self.preview_render_progress_bar.setRange(0, 100)
        self.preview_render_progress_bar.setValue(0)

        form_layout.addRow(self._t("Project"), self.project_name_label)
        form_layout.addRow(self._t("Timeline"), self.timeline_name_label)
        form_layout.addRow(self._t("Start TC / Frame"), self.timeline_start_label)
        form_layout.addRow(self._t("Frame rate"), self.timeline_frame_rate_label)
        form_layout.addRow(self._t("Markers"), self.timeline_marker_count_label)
        form_layout.addRow(self._t("Last preview render"), self.preview_render_label)
        form_layout.addRow(self._t("Render status"), self.preview_render_status_label)
        form_layout.addRow(self._t("Render progress"), self.preview_render_progress_bar)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        self.refresh_context_button = QPushButton(self._t("Refresh Resolve Context"))
        self.refresh_context_button.clicked.connect(self._refresh_resolve_context)

        self.render_preview_button = QPushButton(self._t("Render 720p Preview Now"))
        self.render_preview_button.clicked.connect(self._render_preview_now)

        controls_layout.addWidget(self.refresh_context_button)
        controls_layout.addWidget(self.render_preview_button)
        controls_layout.addStretch(1)

        self.marker_preview = QPlainTextEdit()
        self.marker_preview.setReadOnly(True)
        self.marker_preview.setMinimumHeight(140)
        self.marker_preview.setPlaceholderText(self._t("Markers will appear here after loading the current timeline."))

        outer_layout.addLayout(form_layout)
        outer_layout.addLayout(controls_layout)
        outer_layout.addWidget(self.marker_preview)
        return group

    def _build_gemini_group(self) -> QGroupBox:
        group = QGroupBox(self._t("Gemini"))
        outer_layout = QVBoxLayout(group)
        outer_layout.setSpacing(10)

        layout = QFormLayout()
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.gemini_endpoint_edit = QLineEdit()
        self.gemini_model_edit = QComboBox()
        self.gemini_model_edit.setEditable(True)
        self.gemini_api_key_edit = QLineEdit()
        self.gemini_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_status_label = QLabel(self._t("Not tested yet."))
        self.gemini_status_label.setWordWrap(True)
        self.gemini_analysis_source_label = QLabel(self._t("No preview available yet."))
        self.gemini_analysis_source_label.setWordWrap(True)
        self.analyze_preview_button = QPushButton(self._t("Analyze Last Preview With Gemini"))
        self.analyze_preview_button.clicked.connect(self._analyze_preview_with_gemini)
        self.gemini_analysis_preview = QPlainTextEdit()
        self.gemini_analysis_preview.setReadOnly(True)
        self.gemini_analysis_preview.setMinimumHeight(180)
        self.gemini_analysis_preview.setPlaceholderText(
            self._t("Structured Gemini analysis will appear here after a preview render is available.")
        )

        layout.addRow(self._t("Endpoint"), self.gemini_endpoint_edit)
        layout.addRow(self._t("Model"), self.gemini_model_edit)
        layout.addRow(self._t("API key"), self.gemini_api_key_edit)
        layout.addRow(self._t("Status"), self.gemini_status_label)
        layout.addRow(self._t("Analysis source"), self.gemini_analysis_source_label)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        actions_layout.addWidget(self.analyze_preview_button)
        actions_layout.addStretch(1)

        outer_layout.addLayout(layout)
        outer_layout.addLayout(actions_layout)
        outer_layout.addWidget(self.gemini_analysis_preview)

        self.gemini_endpoint_edit.textChanged.connect(self._mark_dirty)
        self.gemini_model_edit.currentTextChanged.connect(self._mark_dirty)
        self.gemini_api_key_edit.textChanged.connect(self._mark_dirty)

        return group

    def _build_audio_group(self) -> QGroupBox:
        group = QGroupBox(self._t("Audio Provider"))
        outer_layout = QVBoxLayout(group)
        outer_layout.setSpacing(10)

        layout = QFormLayout()
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.audio_provider_combo = QComboBox()
        self.audio_provider_combo.addItem("AIMLAPI-Compatible", "aimlapi")
        self.audio_provider_combo.addItem("SunoAPI", "sunoapi")
        self.audio_base_url_edit = QLineEdit()
        self.audio_model_hint_edit = QLineEdit()
        self.audio_test_endpoint_edit = QLineEdit()
        self.audio_api_key_edit = QLineEdit()
        self.audio_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.audio_status_label = QLabel(self._t("Not tested yet."))
        self.audio_status_label.setWordWrap(True)
        self.audio_analysis_source_label = QLabel(self._t("No Gemini plan available yet."))
        self.audio_analysis_source_label.setWordWrap(True)
        self.generate_audio_button = QPushButton(self._t("Generate Timeline Audio From Last Analysis"))
        self.generate_audio_button.clicked.connect(self._generate_audio_from_analysis)
        self.audio_generation_preview = QPlainTextEdit()
        self.audio_generation_preview.setReadOnly(True)
        self.audio_generation_preview.setMinimumHeight(180)
        self.audio_generation_preview.setPlaceholderText(
            self._t("Generated audio placements will appear here after a Gemini analysis is available.")
        )

        layout.addRow(self._t("Provider"), self.audio_provider_combo)
        layout.addRow(self._t("Base URL"), self.audio_base_url_edit)
        layout.addRow(self._t("Model hint"), self.audio_model_hint_edit)
        layout.addRow(self._t("Test endpoint"), self.audio_test_endpoint_edit)
        layout.addRow(self._t("API key"), self.audio_api_key_edit)
        layout.addRow(self._t("Status"), self.audio_status_label)
        layout.addRow(self._t("Analysis source"), self.audio_analysis_source_label)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        actions_layout.addWidget(self.generate_audio_button)
        actions_layout.addStretch(1)

        outer_layout.addLayout(layout)
        outer_layout.addLayout(actions_layout)
        outer_layout.addWidget(self.audio_generation_preview)

        self.audio_provider_combo.currentIndexChanged.connect(self._handle_audio_provider_changed)
        self.audio_base_url_edit.textChanged.connect(self._mark_dirty)
        self.audio_model_hint_edit.textChanged.connect(self._mark_dirty)
        self.audio_test_endpoint_edit.textChanged.connect(self._mark_dirty)
        self.audio_api_key_edit.textChanged.connect(self._mark_dirty)

        return group

    def _build_gemini_music_group(self) -> QGroupBox:
        group = QGroupBox(self._t("Gemini Music (Lyria 3)"))
        outer_layout = QVBoxLayout(group)
        outer_layout.setSpacing(10)

        layout = QFormLayout()
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.gemini_music_model_combo = QComboBox()
        self.gemini_music_model_combo.setEditable(True)
        self.gemini_music_model_combo.addItem(self._t("Lyria 3 Pro"), "lyria-3-pro-preview")
        self.gemini_music_model_combo.addItem(self._t("Lyria 3 Clip"), "lyria-3-clip-preview")

        self.gemini_music_vocals_combo = QComboBox()
        self.gemini_music_vocals_combo.addItem(self._t("Instrumental only"), "instrumental")
        self.gemini_music_vocals_combo.addItem(self._t("With lyrics"), "lyrics")

        self.gemini_music_output_combo = QComboBox()
        self.gemini_music_output_combo.addItem("MP3", "mp3")
        self.gemini_music_output_combo.addItem("WAV", "wav")

        self.gemini_music_use_images_combo = QComboBox()
        self.gemini_music_use_images_combo.addItem(self._t("Use marker images when flagged"), "true")
        self.gemini_music_use_images_combo.addItem(self._t("Ignore marker images"), "false")

        self.gemini_music_crossfade_edit = QLineEdit()
        self.gemini_music_status_label = QLabel(self._t("Not generated yet."))
        self.gemini_music_status_label.setWordWrap(True)
        self.gemini_music_source_label = QLabel(self._t("No preview available yet."))
        self.gemini_music_source_label.setWordWrap(True)
        self.gemini_music_marker_help_label = QLabel(
            self._t(
                "Use marker names like 'Music Track 1: Farmer John Theme' to define named music lanes. Markers with the same lane are grouped into one generated cue for that lane, and later markers in that lane are treated as in-cue directives. Use structured free text per paragraph such as 'Genre = Western, Scifi', 'Instruments = Banjo, Synth Pad', 'BPM = 85', 'Key = D minor', 'Mood = nostalgic, eerie', 'Song_Structure = Intro, Verse, Chorus', and 'Input = A gentle banjo motif that accelerates over time'. Use '[Stop]' to end naturally at that marker timestamp, or '[StopHard]' for an abrupt exact cut."
            )
        )
        self.gemini_music_marker_help_label.setWordWrap(True)

        layout.addRow(self._t("Model"), self.gemini_music_model_combo)
        layout.addRow(self._t("Vocals"), self.gemini_music_vocals_combo)
        layout.addRow(self._t("Output format"), self.gemini_music_output_combo)
        layout.addRow(self._t("Marker images"), self.gemini_music_use_images_combo)
        layout.addRow(self._t("Crossfade seconds (Resolve)"), self.gemini_music_crossfade_edit)
        layout.addRow(self._t("Source preview"), self.gemini_music_source_label)
        layout.addRow(self._t("Status"), self.gemini_music_status_label)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        self.generate_gemini_music_button = QPushButton(self._t("Generate Timeline Music With Gemini"))
        self.generate_gemini_music_button.clicked.connect(self._generate_music_with_gemini)
        actions_layout.addWidget(self.generate_gemini_music_button)
        actions_layout.addStretch(1)

        self.gemini_music_preview = QPlainTextEdit()
        self.gemini_music_preview.setReadOnly(True)
        self.gemini_music_preview.setMinimumHeight(180)
        self.gemini_music_preview.setPlaceholderText(
            self._t("Gemini music generation results, lyrics, structure text, and placement details will appear here.")
        )

        self.gemini_music_model_combo.currentTextChanged.connect(self._mark_dirty)
        self.gemini_music_vocals_combo.currentIndexChanged.connect(self._mark_dirty)
        self.gemini_music_output_combo.currentIndexChanged.connect(self._mark_dirty)
        self.gemini_music_use_images_combo.currentIndexChanged.connect(self._mark_dirty)
        self.gemini_music_crossfade_edit.textChanged.connect(self._mark_dirty)

        outer_layout.addLayout(layout)
        outer_layout.addWidget(self.gemini_music_marker_help_label)
        outer_layout.addLayout(actions_layout)
        outer_layout.addWidget(self.gemini_music_preview)
        return group

    def _build_paths_group(self) -> QGroupBox:
        group = QGroupBox(self._t("Paths"))
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.output_directory_edit = QLineEdit()
        self.temp_directory_edit = QLineEdit()
        self.temp_retention_days_edit = QLineEdit()

        output_row = self._create_path_row(self.output_directory_edit, self._select_output_directory)
        temp_row = self._create_path_row(self.temp_directory_edit, self._select_temp_directory)

        layout.addRow(self._t("Output directory"), output_row)
        layout.addRow(self._t("Temp directory"), temp_row)
        layout.addRow(self._t("Temp preview retention (days)"), self.temp_retention_days_edit)

        cache_actions = QHBoxLayout()
        cache_actions.setSpacing(8)
        self.delete_preview_cache_button = QPushButton(self._t("Delete preview cache"))
        self.delete_preview_cache_button.clicked.connect(self._delete_preview_cache)
        self.delete_all_temp_cache_button = QPushButton(self._t("Delete all temp cache files"))
        self.delete_all_temp_cache_button.clicked.connect(self._delete_all_temp_cache)
        cache_actions.addWidget(self.delete_preview_cache_button)
        cache_actions.addWidget(self.delete_all_temp_cache_button)
        cache_actions.addStretch(1)

        cache_actions_widget = QWidget()
        cache_actions_widget.setLayout(cache_actions)
        layout.addRow(self._t("Cache actions"), cache_actions_widget)

        self.output_directory_edit.textChanged.connect(self._mark_dirty)
        self.temp_directory_edit.textChanged.connect(self._mark_dirty)
        self.temp_retention_days_edit.textChanged.connect(self._mark_dirty)

        return group

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox(self._t("Status"))
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(group)

        self.status_console = QPlainTextEdit()
        self.status_console.setReadOnly(True)
        self.status_console.setMinimumHeight(120)
        self.status_console.setMaximumHeight(160)
        self.status_console.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout.addWidget(self.status_console)
        return group

    def _check_for_updates_silently(self) -> None:
        self._check_for_updates(silent=True)

    def _check_for_updates_manually(self) -> None:
        self._check_for_updates(silent=False)

    def _check_for_updates(self, *, silent: bool) -> None:
        if self._update_service is None or self._update_check_in_progress:
            return
        self._update_check_in_progress = True
        self.check_updates_button.setEnabled(False)
        if not silent:
            self._append_status(self._t("Checking for CineScore AI updates..."))
        worker = BackgroundTask(lambda: self._update_service.check_for_update(), with_progress=False)
        self._active_workers.add(worker)
        worker.signals.succeeded.connect(lambda result: self._handle_update_check_result(result, silent=silent))
        worker.signals.failed.connect(lambda error: self._handle_update_check_error(error, silent=silent))
        worker.signals.finished.connect(lambda: self._finish_update_check(worker))
        self._thread_pool.start(worker)

    def _finish_update_check(self, worker: BackgroundTask) -> None:
        self._update_check_in_progress = False
        if self._update_service is not None:
            self.check_updates_button.setEnabled(True)
        self._active_workers.discard(worker)

    def _handle_update_check_result(self, result: UpdateCheckResult, *, silent: bool) -> None:
        release = result.latest_release
        if result.update_available and release is not None:
            self._append_status(
                self._t(
                    "Update available: installed {current}, latest {latest}.",
                    current=result.current_version,
                    latest=release.version,
                )
            )
            if not silent or not self._update_dialog_shown:
                self._update_dialog_shown = True
                self._show_update_dialog(result.current_version, release, result.newer_releases)
            return
        if not silent:
            self._append_status(self._t("CineScore AI is already up to date."))
            QMessageBox.information(
                self,
                self._t("Check for updates"),
                self._t("CineScore AI is already up to date."),
            )

    def _handle_update_check_error(self, error_message: str, *, silent: bool) -> None:
        if silent:
            self._append_status(self._t("Update check failed: {error}", error=error_message))
            return
        self._append_status(self._t("Update check failed: {error}", error=error_message))
        QMessageBox.warning(
            self,
            self._t("Check for updates"),
            self._t("Update check failed: {error}", error=error_message),
        )

    def _show_update_dialog(self, current_version: str, release: ReleaseInfo, newer_releases: tuple[ReleaseInfo, ...]) -> None:
        if self._update_service is None:
            return
        dialog = UpdateAvailableDialog(
            parent=self,
            current_version=current_version,
            release=release,
            newer_releases=newer_releases,
            translate=self._t,
            can_self_update=self._update_service.can_start_self_update(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_update_installation(release)

    def _start_update_installation(self, release: ReleaseInfo) -> None:
        if self._update_service is None:
            return
        if not self._update_service.can_start_self_update():
            QMessageBox.information(
                self,
                self._t("Update available"),
                self._t("Automatic update is currently only supported on Windows."),
            )
            return

        answer = QMessageBox.question(
            self,
            self._t("Start update"),
            self._t(
                "DaVinci Resolve will be closed automatically for the update. Save your project first. Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._update_service.start_windows_update(release)
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._t("Update available"),
                self._t("Could not start updater: {error}", error=str(exc)),
            )
            return

        self._append_status(
            self._t(
                "Update helper started. DaVinci Resolve will close automatically. After installation, the helper can reopen Resolve.",
            )
        )
        QMessageBox.information(
            self,
            self._t("Start update"),
            self._t(
                "Update helper started. DaVinci Resolve will close automatically. After installation, the helper can reopen Resolve.",
            ),
        )
        app = QApplication.instance()
        if app is not None:
            app.closeAllWindows()

    def _create_path_row(self, line_edit: QLineEdit, callback: object) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        browse_button = QPushButton(self._t("Browse"))
        browse_button.clicked.connect(callback)

        layout.addWidget(line_edit, 1)
        layout.addWidget(browse_button)
        return container

    def _apply_runtime_state(self) -> None:
        self.resize(self._loaded_config.ui.window_width, self._loaded_config.ui.window_height)
        self.runtime_label.setText(
            self._t(
                "Runtime: {runtime}. {summary}",
                runtime=self._t(self._resolve_adapter.runtime_name),
                summary=self._t(self._resolve_adapter.get_environment_summary()),
            )
        )
        self.version_label.setText(
            self._t(
                "Installed version: {version}",
                version=get_app_version(),
            )
        )

        if self._secret_store.is_persistent:
            self.secret_backend_label.setText(
                self._t(
                    "Secrets are stored in the OS keychain via '{backend}'.",
                    backend=self._secret_store.backend_name,
                )
            )
            self.secret_backend_label.setStyleSheet("color: #1f5f2f;")
        else:
            self.secret_backend_label.setText(
                self._t("No persistent keychain backend was found. Secrets stay in memory for this session only.")
            )
            self.secret_backend_label.setStyleSheet("color: #8a5a00; font-weight: 600;")

        self._set_dirty(False)
        self._append_status(self._t("Settings loaded."))
        self._append_status(
            self._t(
                "Resolve context can now be refreshed, preview renders can run to completion, Gemini can analyze the latest preview, Gemini Lyria can compose marker-driven music, and optional external audio providers can place generated audio back into Resolve."
            )
        )

    def _open_discord_community(self) -> None:
        if not QDesktopServices.openUrl(QUrl(self.DISCORD_INVITE_URL)):
            self._append_status(
                self._t("Could not open Discord community link: {url}", url=self.DISCORD_INVITE_URL)
            )
            QMessageBox.warning(
                self,
                self._t("Discord"),
                self._t("Could not open Discord community link: {url}", url=self.DISCORD_INVITE_URL),
            )

    def eventFilter(self, watched: object, event: object) -> bool:
        if watched is self.discord_button and isinstance(event, QEvent):
            if event.type() == QEvent.Type.Enter:
                self._set_discord_button_icon(hovered=True)
            elif event.type() == QEvent.Type.Leave:
                self._set_discord_button_icon(hovered=False)
            elif event.type() == QEvent.Type.MouseButtonPress:
                self._set_discord_button_icon(hovered=True)
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._set_discord_button_icon(hovered=self.discord_button.underMouse())
        return super().eventFilter(watched, event)

    def _set_discord_button_icon(self, *, hovered: bool) -> None:
        if hovered and not self._discord_icon_hover.isNull():
            self.discord_button.setIcon(self._discord_icon_hover)
            return
        if not self._discord_icon_default.isNull():
            self.discord_button.setIcon(self._discord_icon_default)

    def _populate_form(self, config: AppConfig) -> None:
        self._is_loading_form = True
        try:
            self.gemini_endpoint_edit.setText(config.gemini.endpoint)
            self._set_editable_combo_text(self.gemini_model_edit, config.gemini.model)
            self.gemini_api_key_edit.setText(self._secret_store.get_secret(GEMINI_API_KEY_SECRET) or "")
            self._set_combo_value(self.gemini_music_model_combo, config.gemini_music.model)
            self._set_combo_value(self.gemini_music_vocals_combo, config.gemini_music.vocals_mode)
            self._set_combo_value(self.gemini_music_output_combo, config.gemini_music.output_format)
            self._set_combo_value(
                self.gemini_music_use_images_combo,
                "true" if config.gemini_music.use_marker_images else "false",
            )
            self.gemini_music_crossfade_edit.setText(str(config.gemini_music.crossfade_seconds))

            self._set_combo_value(self.audio_provider_combo, config.audio_provider.provider_name)
            self.audio_base_url_edit.setText(config.audio_provider.base_url)
            self.audio_model_hint_edit.setText(config.audio_provider.model_hint)
            self.audio_test_endpoint_edit.setText(config.audio_provider.test_endpoint)
            self.audio_api_key_edit.setText(
                self._secret_store.get_secret(get_audio_provider_secret_name(config.audio_provider.provider_name)) or ""
            )

            self.output_directory_edit.setText(config.paths.output_directory)
            self.temp_directory_edit.setText(config.paths.temp_directory)
            self.temp_retention_days_edit.setText(str(config.paths.temp_preview_retention_days))
            self.gemini_status_label.setText(self._t("Not tested yet."))
            self.gemini_music_status_label.setText(self._t("Not generated yet."))
            self.audio_status_label.setText(self._t("Not tested yet."))
            self.gemini_analysis_preview.setPlainText("")
            self.gemini_music_preview.setPlainText("")
            self.audio_generation_preview.setPlainText("")
            self._set_analysis_source_text(self._last_preview_render.target_path if self._last_preview_render else None)
            self._set_gemini_music_source_text(self._last_preview_render.target_path if self._last_preview_render else None)
            self._set_audio_analysis_source_text(
                self._last_gemini_analysis_result.preview_path if self._last_gemini_analysis_result is not None else None
            )
        finally:
            self._is_loading_form = False

    def _set_combo_value(self, combo_box: QComboBox, value: str) -> None:
        index = combo_box.findData(value)
        if index >= 0:
            combo_box.setCurrentIndex(index)
            return
        text_index = combo_box.findText(value)
        combo_box.setCurrentIndex(text_index if text_index >= 0 else 0)

    def _set_editable_combo_text(self, combo_box: QComboBox, value: str) -> None:
        text = value.strip()
        if not text:
            combo_box.setEditText("")
            return
        text_index = combo_box.findText(text)
        if text_index < 0:
            combo_box.addItem(text, text)
            text_index = combo_box.findText(text)
        combo_box.setCurrentIndex(text_index)
        combo_box.setEditText(text)

    def _replace_combo_items(self, combo_box: QComboBox, values: list[str], selected_value: str) -> None:
        current_selection = selected_value.strip() or combo_box.currentText().strip()
        unique_values = [value for value in dict.fromkeys(value.strip() for value in values if value.strip())]
        if current_selection and current_selection not in unique_values:
            unique_values.insert(0, current_selection)
        combo_box.blockSignals(True)
        try:
            combo_box.clear()
            for value in unique_values:
                combo_box.addItem(value, value)
            self._set_editable_combo_text(combo_box, current_selection)
        finally:
            combo_box.blockSignals(False)

    def _update_gemini_model_catalog(self, analysis_models: list[str], music_models: list[str]) -> None:
        self._replace_combo_items(
            self.gemini_model_edit,
            analysis_models,
            self.gemini_model_edit.currentText(),
        )
        canonical_music_models = ["lyria-3-pro-preview", "lyria-3-clip-preview"]
        merged_music_models = list(dict.fromkeys(canonical_music_models + [model for model in music_models if model]))
        if merged_music_models:
            self._replace_combo_items(
                self.gemini_music_model_combo,
                merged_music_models,
                self._selected_combo_value(self.gemini_music_model_combo),
            )

    def _selected_combo_value(self, combo_box: QComboBox) -> str:
        data = combo_box.currentData()
        if data is not None:
            return str(data).strip()
        return combo_box.currentText().strip()

    def _parse_float_or_default(self, value: str, fallback: float) -> float:
        try:
            parsed = float(value.strip())
        except (TypeError, ValueError):
            return fallback
        return max(0.0, parsed)

    def _parse_int_or_default(self, value: str, fallback: int) -> int:
        try:
            parsed = int(value.strip())
        except (TypeError, ValueError):
            return fallback
        return max(0, parsed)

    def _handle_audio_provider_changed(self, *_args) -> None:
        if self._is_loading_form:
            return

        defaults = get_default_audio_provider_settings(self._selected_audio_provider_name())
        self.audio_base_url_edit.setText(defaults.base_url)
        self.audio_model_hint_edit.setText(defaults.model_hint)
        self.audio_test_endpoint_edit.setText(defaults.test_endpoint)
        self._mark_dirty()

    def _collect_config(self) -> AppConfig:
        audio_settings = AudioProviderSettings(
            provider_name=self._selected_audio_provider_name(),
            base_url=self.audio_base_url_edit.text().strip(),
            model_hint=self.audio_model_hint_edit.text().strip(),
            test_endpoint=self.audio_test_endpoint_edit.text().strip() or "/models",
            timeout_seconds=self._loaded_config.audio_provider.timeout_seconds,
        )
        gemini_settings = GeminiSettings(
            model=self.gemini_model_edit.currentText().strip(),
            endpoint=self.gemini_endpoint_edit.text().strip(),
            timeout_seconds=self._loaded_config.gemini.timeout_seconds,
        )
        gemini_music_settings = GeminiMusicSettings(
            model=self._selected_combo_value(self.gemini_music_model_combo),
            vocals_mode=str(self.gemini_music_vocals_combo.currentData()),
            output_format=str(self.gemini_music_output_combo.currentData()),
            use_marker_images=str(self.gemini_music_use_images_combo.currentData()) == "true",
            crossfade_seconds=self._parse_float_or_default(
                self.gemini_music_crossfade_edit.text(),
                self._loaded_config.gemini_music.crossfade_seconds,
            ),
            max_images=self._loaded_config.gemini_music.max_images,
        )
        return AppConfig(
            active_audio_provider=self._selected_audio_provider_name(),
            gemini=gemini_settings,
            gemini_music=gemini_music_settings,
            audio_provider=audio_settings,
            paths=replace(
                self._loaded_config.paths,
                output_directory=self.output_directory_edit.text().strip(),
                temp_directory=self.temp_directory_edit.text().strip(),
                temp_preview_retention_days=self._parse_int_or_default(
                    self.temp_retention_days_edit.text(),
                    self._loaded_config.paths.temp_preview_retention_days,
                ),
            ),
            ui=replace(
                self._loaded_config.ui,
                window_width=max(self.width(), 860),
                window_height=max(self.height(), 680),
            ),
        )

    def _selected_audio_provider_name(self) -> str:
        return str(self.audio_provider_combo.currentData())

    def _save_settings(self) -> None:
        config = self._collect_config()
        self._config_store.save(config)

        gemini_api_key = self.gemini_api_key_edit.text().strip()
        if gemini_api_key:
            self._secret_store.set_secret(GEMINI_API_KEY_SECRET, gemini_api_key)
        else:
            self._secret_store.delete_secret(GEMINI_API_KEY_SECRET)

        audio_secret_name = get_audio_provider_secret_name(config.audio_provider.provider_name)
        audio_api_key = self.audio_api_key_edit.text().strip()
        if audio_api_key:
            self._secret_store.set_secret(audio_secret_name, audio_api_key)
        else:
            self._secret_store.delete_secret(audio_secret_name)

        self._loaded_config = config
        self._set_dirty(False)
        self._append_status(
            self._t("Saved configuration to {path}.", path=self._config_store.config_file_path)
        )

        if not self._secret_store.is_persistent:
            self._append_status(self._t("Secrets are only available for the current app session."))

    def _discard_changes(self) -> None:
        self._loaded_config = self._config_store.load()
        self._populate_form(self._loaded_config)
        self._set_dirty(False)
        self._append_status(self._t("Discarded unsaved changes."))

    def _test_gemini_connection(self) -> None:
        settings = GeminiSettings(
            model=self.gemini_model_edit.currentText().strip(),
            endpoint=self.gemini_endpoint_edit.text().strip(),
            timeout_seconds=self._loaded_config.gemini.timeout_seconds,
        )
        api_key = self.gemini_api_key_edit.text()
        self.gemini_status_label.setText(self._t("Testing..."))
        self._run_background_task(
            button=self.test_gemini_button,
            start_message=self._t("Testing Gemini connection..."),
            callback=lambda: self._connection_test_service.test_gemini(api_key=api_key, settings=settings),
            result_handler=self._handle_gemini_result,
        )

    def _test_audio_connection(self) -> None:
        settings = AudioProviderSettings(
            provider_name=self._selected_audio_provider_name(),
            base_url=self.audio_base_url_edit.text().strip(),
            model_hint=self.audio_model_hint_edit.text().strip(),
            test_endpoint=self.audio_test_endpoint_edit.text().strip() or "/models",
            timeout_seconds=self._loaded_config.audio_provider.timeout_seconds,
        )
        api_key = self.audio_api_key_edit.text()
        self.audio_status_label.setText(self._t("Testing..."))
        self._run_background_task(
            button=self.test_audio_button,
            start_message=self._t("Testing audio provider connection..."),
            callback=lambda: self._connection_test_service.test_audio_provider(api_key=api_key, settings=settings),
            result_handler=self._handle_audio_result,
        )

    def _generate_audio_from_analysis(self) -> None:
        if self._last_gemini_analysis_result is None:
            self.audio_status_label.setText(self._t("Run Gemini analysis first."))
            self.audio_generation_preview.setPlainText("")
            self._append_status(self._t("Audio generation skipped because no Gemini analysis result is available yet."))
            return

        config = self._collect_config()
        audio_api_key = self.audio_api_key_edit.text().strip()

        self.audio_status_label.setText(self._t("Generating audio..."))
        self.audio_generation_preview.setPlainText("")
        self._last_audio_progress_message = ""
        self._set_audio_analysis_source_text(self._last_gemini_analysis_result.preview_path)

        self._run_background_task(
            button=self.generate_audio_button,
            start_message=self._t("Starting audio generation from the latest Gemini analysis..."),
            callback=lambda progress: self._run_audio_generation(config, audio_api_key, progress),
            result_handler=self._handle_audio_generation_result,
            error_handler=self._handle_audio_generation_error,
            progress_handler=self._handle_audio_generation_progress,
        )

    def _analyze_preview_with_gemini(self) -> None:
        config = self._collect_config()
        api_key = self.gemini_api_key_edit.text().strip()
        preferred_preview_path = self._last_preview_render.target_path if self._last_preview_render is not None else None

        self.gemini_status_label.setText(self._t("Analyzing preview..."))
        self._last_gemini_progress_message = ""
        self.gemini_analysis_preview.setPlainText("")
        self._set_analysis_source_text(preferred_preview_path)

        self._run_background_task(
            button=self.analyze_preview_button,
            start_message=self._t("Starting Gemini video analysis for the latest preview render..."),
            callback=lambda progress: self._run_gemini_analysis(config, api_key, preferred_preview_path, progress),
            result_handler=self._handle_gemini_analysis_result,
            error_handler=self._handle_gemini_analysis_error,
            progress_handler=self._handle_gemini_analysis_progress,
        )

    def _generate_music_with_gemini(
        self,
        *,
        output_format_override: str | None = None,
        retry_reason: str | None = None,
    ) -> None:
        config = self._collect_config()
        api_key = self.gemini_api_key_edit.text().strip()
        preferred_preview_path = self._last_preview_render.target_path if self._last_preview_render is not None else None

        self.gemini_music_status_label.setText(self._t("Generating music..."))
        self.gemini_music_preview.setPlainText("")
        self._last_gemini_music_progress_message = ""
        self._set_gemini_music_source_text(preferred_preview_path)

        if output_format_override:
            start_message = self._t(
                "Retrying Gemini music generation with MP3 after WAV failure..."
            )
        else:
            start_message = self._t("Starting Gemini music generation from timeline markers...")

        if retry_reason:
            self._append_status(
                self._t("WAV fallback reason: {reason}", reason=retry_reason)
            )

        self._run_background_task(
            button=self.generate_gemini_music_button,
            start_message=start_message,
            callback=lambda progress: self._run_gemini_music_generation(
                config,
                api_key,
                preferred_preview_path,
                progress,
                output_format_override=output_format_override,
            ),
            result_handler=self._handle_gemini_music_generation_result,
            error_handler=self._handle_gemini_music_generation_error,
            progress_handler=self._handle_gemini_music_generation_progress,
        )

    def _refresh_resolve_context(self) -> None:
        self._run_background_task(
            button=self.refresh_context_button,
            start_message=self._t("Loading Resolve timeline context..."),
            callback=self._resolve_workflow_service.load_current_timeline_context,
            result_handler=self._handle_resolve_context_result,
            error_handler=self._handle_resolve_context_error,
        )

    def _render_preview_now(self) -> None:
        config = self._collect_config()
        self.preview_render_label.setText(self._t("Preparing preview render..."))
        self.preview_render_status_label.setText(self._t("Starting..."))
        self.preview_render_progress_bar.setValue(0)
        self._last_preview_progress_message = ""
        self._run_background_task(
            button=self.render_preview_button,
            start_message=self._t("Starting 720p preview render and waiting for completion..."),
            callback=lambda progress: self._resolve_workflow_service.render_preview_and_wait(
                config,
                progress_callback=progress,
            ),
            result_handler=self._handle_preview_render_execution_result,
            error_handler=self._handle_preview_render_error,
            progress_handler=self._handle_preview_render_progress,
        )

    def _run_background_task(
        self,
        button: QPushButton,
        start_message: str,
        callback: object,
        result_handler: object,
        error_handler: object | None = None,
        progress_handler: object | None = None,
    ) -> None:
        self._append_status(start_message)
        button.setEnabled(False)

        worker = BackgroundTask(callback, with_progress=progress_handler is not None)  # type: ignore[arg-type]
        self._active_workers.add(worker)

        worker.signals.succeeded.connect(result_handler)  # type: ignore[arg-type]
        if progress_handler is not None:
            worker.signals.progress.connect(progress_handler)  # type: ignore[arg-type]
        worker.signals.failed.connect(lambda error: self._handle_task_error(button, error, error_handler))
        worker.signals.finished.connect(lambda: self._finish_worker(button, worker))

        self._thread_pool.start(worker)

    def _finish_worker(self, button: QPushButton, worker: BackgroundTask) -> None:
        button.setEnabled(True)
        self._active_workers.discard(worker)

    def _handle_task_error(self, button: QPushButton, error_message: str, error_handler: object | None) -> None:
        button.setEnabled(True)
        self._append_status(self._t("Task failed: {error}", error=error_message))
        self._try_open_manual_audio_import_folder(error_message)
        if callable(error_handler):
            error_handler(error_message)
            return
        if button is self.test_gemini_button:
            self.gemini_status_label.setText(error_message)
        elif button is self.generate_gemini_music_button:
            self.gemini_music_status_label.setText(error_message)
        elif button is self.test_audio_button:
            self.audio_status_label.setText(error_message)
        elif button is self.generate_audio_button:
            self.audio_status_label.setText(error_message)
        elif button is self.render_preview_button:
            self.preview_render_status_label.setText(error_message)

    def _try_open_manual_audio_import_folder(self, error_message: str) -> None:
        normalized_error = error_message.lower()
        if "could not import audio file" not in normalized_error:
            return

        audio_path = self._extract_audio_path_from_error(error_message)
        if audio_path is None:
            return

        folder = audio_path.parent
        if not folder.exists():
            return

        opened = self._open_in_file_explorer(folder)
        if opened:
            self._append_status(
                self._t(
                    "Opened audio folder for manual import: {path}",
                    path=str(folder),
                )
            )
            self._append_status(self._t("Drag the generated audio file into the Resolve Media Pool manually."))

    def _extract_audio_path_from_error(self, error_message: str) -> Path | None:
        # Resolve errors quote the failing path, e.g. 'C:\\...\\track_01_foo.wav'
        for pattern in (
            r"'([^']+\\.(?:wav|mp3|aif|aiff|flac|m4a))'",
            r'"([^"]+\\.(?:wav|mp3|aif|aiff|flac|m4a))"',
        ):
            match = re.search(pattern, error_message, flags=re.IGNORECASE)
            if match:
                return Path(match.group(1))
        return None

    def _open_in_file_explorer(self, folder: Path) -> bool:
        try:
            if os.name == "nt" and hasattr(os, "startfile"):
                os.startfile(str(folder))  # type: ignore[attr-defined]
                return True
            if os.name == "posix":
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, str(folder)])
                return True
        except Exception:
            return False
        return False

    def _handle_gemini_result(self, result: ConnectionTestResult) -> None:
        self.gemini_status_label.setText(result.message)
        analysis_models = result.details.get("analysis_models", [])
        music_models = result.details.get("music_models", [])
        if isinstance(analysis_models, list) or isinstance(music_models, list):
            self._update_gemini_model_catalog(
                [str(model) for model in analysis_models] if isinstance(analysis_models, list) else [],
                [str(model) for model in music_models] if isinstance(music_models, list) else [],
            )
        self._append_status(result.message)

    def _handle_audio_result(self, result: ConnectionTestResult) -> None:
        self.audio_status_label.setText(result.message)
        self._append_status(result.message)

    def _handle_resolve_context_result(self, context: ResolveTimelineContext) -> None:
        self._current_context = context
        self.project_name_label.setText(context.project_name)
        self.timeline_name_label.setText(context.timeline_name)
        self.timeline_start_label.setText(f"{context.start_timecode} / frame {context.start_frame}")
        self.timeline_frame_rate_label.setText(f"{context.frame_rate:.3f} fps")
        self.timeline_marker_count_label.setText(
            f"{context.marker_count} markers across {context.video_track_count} video and {context.audio_track_count} audio tracks"
        )
        self.marker_preview.setPlainText(self._format_marker_preview(context))
        self._append_status(
            self._t(
                "Loaded timeline '{timeline}' from project '{project}' with {count} markers.",
                timeline=context.timeline_name,
                project=context.project_name,
                count=context.marker_count,
            )
        )

    def _handle_resolve_context_error(self, error_message: str) -> None:
        self._current_context = None
        self.project_name_label.setText(self._t("Unavailable"))
        self.timeline_name_label.setText(self._t("Unavailable"))
        self.timeline_start_label.setText(self._t("Unavailable"))
        self.timeline_frame_rate_label.setText(self._t("Unavailable"))
        self.timeline_marker_count_label.setText(error_message)
        self.marker_preview.setPlainText("")

    def _handle_preview_render_error(self, error_message: str) -> None:
        self.preview_render_label.setText(error_message)
        self.preview_render_status_label.setText(error_message)

    def _handle_preview_render_progress(self, update: PreviewRenderProgressUpdate) -> None:
        if update.target_path:
            self.preview_render_label.setText(update.target_path)
        status_text = update.status or update.phase.title()
        self.preview_render_status_label.setText(status_text)
        if update.completion_percentage is not None:
            bounded = max(0, min(100, int(round(update.completion_percentage))))
            self.preview_render_progress_bar.setValue(bounded)
        if update.message and update.message != self._last_preview_progress_message:
            self._append_status(update.message)
            self._last_preview_progress_message = update.message

    def _handle_preview_render_execution_result(self, result: PreviewRenderExecutionResult) -> None:
        self._last_preview_render = result.job
        self.preview_render_label.setText(result.job.target_path)
        final_status = result.final_status.status
        self.preview_render_status_label.setText(final_status)
        self._set_analysis_source_text(result.job.target_path)
        self._set_gemini_music_source_text(result.job.target_path)
        if result.final_status.completion_percentage is not None:
            self.preview_render_progress_bar.setValue(max(0, min(100, int(round(result.final_status.completion_percentage)))))
        if result.timed_out:
            self._append_status(f"Preview render job '{result.job.job_id}' timed out while waiting for completion.")
            return
        self._append_status(
            f"Preview render job '{result.job.job_id}' finished with status '{final_status}'. Output path: {result.job.target_path}"
        )

    def _run_gemini_analysis(
        self,
        config: AppConfig,
        api_key: str,
        preferred_preview_path: str | None,
        progress_callback,
    ) -> GeminiVideoAnalysisResult:
        preview_path = self._resolve_workflow_service.resolve_preview_path(config, preferred_preview_path)
        timeline_context = self._current_context or self._resolve_workflow_service.load_current_timeline_context()
        return self._gemini_video_analysis_service.analyze_preview(
            api_key=api_key,
            settings=config.gemini,
            timeline_context=timeline_context,
            preview_path=preview_path,
            progress_callback=progress_callback,
        )

    def _run_gemini_music_generation(
        self,
        config: AppConfig,
        api_key: str,
        preferred_preview_path: str | None,
        progress_callback,
        output_format_override: str | None = None,
    ) -> GeminiMusicGenerationResult:
        preview_path = self._resolve_workflow_service.resolve_preview_path(config, preferred_preview_path)
        timeline_context = self._current_context or self._resolve_workflow_service.load_current_timeline_context()
        music_settings = config.gemini_music
        if output_format_override:
            music_settings = replace(music_settings, output_format=output_format_override)
        return self._gemini_music_generation_service.generate_from_timeline(
            api_key=api_key,
            gemini_settings=config.gemini,
            music_settings=music_settings,
            timeline_context=timeline_context,
            preview_path=preview_path,
            output_directory=config.paths.output_directory,
            analysis_result=self._last_gemini_analysis_result,
            progress_callback=progress_callback,
        )

    def _run_audio_generation(
        self,
        config: AppConfig,
        api_key: str,
        progress_callback,
    ) -> AudioCompositionResult:
        timeline_context = self._current_context or self._resolve_workflow_service.load_current_timeline_context()
        assert self._last_gemini_analysis_result is not None
        return self._audio_workflow_service.compose_from_analysis(
            api_key=api_key,
            settings=config.audio_provider,
            timeline_context=timeline_context,
            analysis_result=self._last_gemini_analysis_result,
            output_directory=config.paths.output_directory,
            progress_callback=progress_callback,
        )

    def _handle_gemini_analysis_progress(self, update: GeminiAnalysisProgressUpdate) -> None:
        if update.preview_path:
            self._set_analysis_source_text(update.preview_path)
        if update.message:
            self.gemini_status_label.setText(update.message)
            if update.message != self._last_gemini_progress_message:
                self._append_status(update.message)
                self._last_gemini_progress_message = update.message

    def _handle_gemini_analysis_result(self, result: GeminiVideoAnalysisResult) -> None:
        self._last_gemini_analysis_result = result
        self.gemini_status_label.setText(self._t("Gemini analysis completed."))
        self._set_analysis_source_text(result.preview_path)
        self._set_audio_analysis_source_text(result.preview_path)
        self._set_gemini_music_source_text(result.preview_path)
        self.gemini_analysis_preview.setPlainText(json.dumps(result.to_display_dict(), indent=2))
        self._append_status(self._t("Gemini analysis completed for {preview_path}.", preview_path=result.preview_path))

    def _handle_gemini_analysis_error(self, error_message: str) -> None:
        self.gemini_status_label.setText(error_message)
        self.gemini_analysis_preview.setPlainText("")

    def _handle_gemini_music_generation_progress(self, update: GeminiMusicProgressUpdate) -> None:
        if update.message:
            self.gemini_music_status_label.setText(update.message)
            if update.message != self._last_gemini_music_progress_message:
                self._append_status(update.message)
                self._last_gemini_music_progress_message = update.message

    def _handle_gemini_music_generation_result(self, result: GeminiMusicGenerationResult) -> None:
        self._last_gemini_music_result = result
        self.gemini_music_status_label.setText(self._t("Gemini music generation completed."))
        self.gemini_music_preview.setPlainText(json.dumps(result.to_display_dict(), indent=2))
        self._append_status(
            self._t("Gemini music generated {count} cue(s) and placed them back into Resolve.", count=len(result.cues))
        )
        wav_count = sum(1 for cue in result.cues if cue.output_path.lower().endswith(".wav"))
        mp3_count = sum(1 for cue in result.cues if cue.output_path.lower().endswith(".mp3"))
        self._append_status(
            self._t(
                "Gemini music output summary: requested {requested}. Saved files -> WAV: {wav_count}, MP3: {mp3_count}.",
                requested=result.output_format.upper(),
                wav_count=wav_count,
                mp3_count=mp3_count,
            )
        )
        for warning in result.warnings:
            self._append_status(self._t("Warning: {warning}", warning=warning))

    def _handle_gemini_music_generation_error(self, error_message: str) -> None:
        self.gemini_music_status_label.setText(error_message)
        self.gemini_music_preview.setPlainText("")
        if not self._should_offer_mp3_fallback(error_message):
            return

        reason = self._classify_wav_error_reason(error_message)
        answer = QMessageBox.question(
            self,
            self._t("WAV generation failed"),
            self._t(
                "WAV generation failed due to:\n{reason}\n\nWould you like to retry once with MP3 instead?",
                reason=reason,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._append_status(self._t("MP3 fallback was declined after WAV failure."))
            return

        self._append_status(self._t("MP3 fallback accepted. Retrying Gemini music generation."))
        self._generate_music_with_gemini(output_format_override="mp3", retry_reason=reason)

    def _should_offer_mp3_fallback(self, error_message: str) -> bool:
        requested_format = self._selected_combo_value(self.gemini_music_output_combo).strip().lower()
        if requested_format != "wav":
            return False

        normalized = error_message.lower()
        return (
            "requested wav but gemini returned" in normalized
            or "strict wav mode rejected" in normalized
            or "response_mime_type" in normalized
            or "responsemimetype" in normalized
            or "audio/wav" in normalized
        )

    def _classify_wav_error_reason(self, error_message: str) -> str:
        normalized = error_message.lower()
        if "response_mime_type" in normalized or "responsemimetype" in normalized:
            return self._t("Error X: Gemini rejected the WAV response MIME parameter.")
        if "requested wav but gemini returned" in normalized or "strict wav mode rejected" in normalized:
            return self._t("Error Y: Gemini returned non-WAV audio while WAV was requested.")
        return self._t("WAV generation failed due to a WAV format/API mismatch.")

    def _handle_audio_generation_progress(self, update: AudioGenerationProgressUpdate) -> None:
        if update.message:
            self.audio_status_label.setText(update.message)
            if update.message != self._last_audio_progress_message:
                self._append_status(update.message)
                self._last_audio_progress_message = update.message

    def _handle_audio_generation_result(self, result: AudioCompositionResult) -> None:
        self._last_audio_composition_result = result
        self.audio_status_label.setText(self._t("Audio generation completed."))
        self.audio_generation_preview.setPlainText(json.dumps(result.to_display_dict(), indent=2))
        self._append_status(
            self._t(
                "Generated and placed {count} audio segment(s) on Resolve track {track}.",
                count=len(result.segments),
                track=result.track_index,
            )
        )
        for warning in result.warnings:
            self._append_status(self._t("Warning: {warning}", warning=warning))

    def _handle_audio_generation_error(self, error_message: str) -> None:
        self.audio_status_label.setText(error_message)
        self.audio_generation_preview.setPlainText("")

    def _format_marker_preview(self, context: ResolveTimelineContext) -> str:
        if not context.markers:
            return self._t("No markers were found on the active timeline.")

        lines = []
        for marker in context.markers:
            title = marker.name or self._t("Untitled marker")
            note = marker.note or self._t("No note")
            keyword_suffix = (
                f" | {self._t('keywords: {keywords}', keywords=', '.join(marker.keywords))}"
                if marker.keywords
                else ""
            )
            lines.append(
                f"{marker.timestamp} | {marker.color or self._t('No color')} | {title} | {note}{keyword_suffix}"
            )
        return "\n".join(lines)

    def _select_output_directory(self) -> None:
        self._select_directory_into(self.output_directory_edit, self._t("Choose output directory"))

    def _select_temp_directory(self) -> None:
        self._select_directory_into(self.temp_directory_edit, self._t("Choose temp directory"))

    def _delete_preview_cache(self) -> None:
        temp_dir = Path(self.temp_directory_edit.text().strip() or self._loaded_config.paths.temp_directory)
        if not temp_dir.exists():
            self._append_status(self._t("Temp cache directory does not exist: {path}", path=str(temp_dir)))
            return

        deleted_count = 0
        for candidate in temp_dir.glob("cinescore-preview_*.mp4"):
            try:
                candidate.unlink()
                deleted_count += 1
            except OSError:
                continue

        self._append_status(
            self._t(
                "Deleted {count} preview cache file(s) from {path}.",
                count=deleted_count,
                path=str(temp_dir),
            )
        )

    def _delete_all_temp_cache(self) -> None:
        temp_dir = Path(self.temp_directory_edit.text().strip() or self._loaded_config.paths.temp_directory)
        if not temp_dir.exists():
            self._append_status(self._t("Temp cache directory does not exist: {path}", path=str(temp_dir)))
            return

        deleted_entries = 0
        for entry in list(temp_dir.iterdir()):
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                deleted_entries += 1
            except OSError:
                continue

        self._append_status(
            self._t(
                "Deleted {count} temp cache entries from {path}.",
                count=deleted_entries,
                path=str(temp_dir),
            )
        )

    def _select_directory_into(self, field: QLineEdit, title: str) -> None:
        current_value = field.text().strip()
        start_dir = current_value if current_value else str(Path.home())
        selected_dir = QFileDialog.getExistingDirectory(self, title, start_dir)
        if selected_dir:
            field.setText(selected_dir)

    def _mark_dirty(self) -> None:
        if self._is_loading_form:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        suffix = " *" if dirty else ""
        self.setWindowTitle(f"{self._t('CineScore AI Settings')}{suffix}")
        self.save_button.setEnabled(dirty)
        self.discard_button.setEnabled(dirty)

    def _append_status(self, message: str) -> None:
        self.status_console.appendPlainText(message)

    def _set_analysis_source_text(self, preview_path: str | None) -> None:
        self.gemini_analysis_source_label.setText(preview_path or self._t("No preview available yet."))

    def _set_gemini_music_source_text(self, preview_path: str | None) -> None:
        self.gemini_music_source_label.setText(preview_path or self._t("No preview available yet."))

    def _set_audio_analysis_source_text(self, preview_path: str | None) -> None:
        self.audio_analysis_source_label.setText(preview_path or self._t("No Gemini plan available yet."))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if not self._dirty:
            event.accept()
            return

        answer = QMessageBox.question(
            self,
            self._t("Unsaved changes"),
            self._t("Discard unsaved changes and close the window?"),
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Discard:
            event.accept()
            return
        event.ignore()

    def _apply_resolve_theme(self) -> None:
        """Apply a DaVinci Resolve-inspired dark theme to the application."""
        stylesheet = """
        /* Main Window */
        QMainWindow {
            background-color: #1a1a1a;
            color: #d0d0d0;
        }

        /* Central Widget */
        QWidget {
            background-color: #1a1a1a;
            color: #d0d0d0;
        }

        /* Labels */
        QLabel {
            color: #d0d0d0;
            background-color: transparent;
        }

        /* Line Edits */
        QLineEdit {
            background-color: #2a2a2a;
            color: #d0d0d0;
            border: 1px solid #3a3a3a;
            border-radius: 3px;
            padding: 4px;
            selection-background-color: #4a9c9c;
            selection-color: #1a1a1a;
        }

        QLineEdit:focus {
            border: 1px solid #4a9c9c;
            background-color: #2f2f2f;
        }

        QLineEdit:disabled {
            color: #606060;
            background-color: #1f1f1f;
        }

        /* Text Edits */
        QPlainTextEdit {
            background-color: #1f1f1f;
            color: #d0d0d0;
            border: 1px solid #3a3a3a;
            border-radius: 3px;
        }

        QPlainTextEdit:focus {
            border: 1px solid #4a9c9c;
        }

        /* Combo Boxes */
        QComboBox {
            background-color: #2a2a2a;
            color: #d0d0d0;
            border: 1px solid #3a3a3a;
            border-radius: 3px;
            padding: 4px;
            selection-background-color: #4a9c9c;
        }

        QComboBox:focus {
            border: 1px solid #4a9c9c;
            background-color: #2f2f2f;
        }

        QComboBox::drop-down {
            border-left: 1px solid #3a3a3a;
            background-color: #2a2a2a;
            width: 20px;
        }

        QComboBox::down-arrow {
            image: none;
            border: none;
        }

        QComboBox QAbstractItemView {
            background-color: #2a2a2a;
            color: #d0d0d0;
            border: 1px solid #3a3a3a;
            selection-background-color: #4a9c9c;
            selection-color: #1a1a1a;
            padding: 0px;
        }

        /* Buttons */
        QPushButton {
            background-color: #3a3a3a;
            color: #d0d0d0;
            border: 1px solid #4a4a4a;
            border-radius: 3px;
            padding: 5px 15px;
            font-weight: 500;
            min-width: 60px;
            min-height: 24px;
        }

        QPushButton:hover {
            background-color: #4a4a4a;
            border: 1px solid #5a5a5a;
        }

        QPushButton:pressed {
            background-color: #2a4a4a;
            border: 1px solid #4a9c9c;
        }

        QPushButton:focus {
            outline: 1px solid #4a9c9c;
        }

        QPushButton#discordButton:focus {
            outline: none;
            border: none;
        }

        QPushButton:default {
            background-color: #d65d3e;
            color: #ffffff;
            border: 1px solid #e67d5e;
            font-weight: 600;
        }

        QPushButton:default:hover {
            background-color: #e67d5e;
            border: 1px solid #f69d7e;
        }

        QPushButton:default:pressed {
            background-color: #b63d1e;
            border: 1px solid #d65d3e;
        }

        QPushButton:disabled {
            background-color: #262626;
            color: #606060;
            border: 1px solid #323232;
        }

        QPushButton#discordButton {
            background-color: transparent;
            border: none;
            padding: 0px;
            min-width: 44px;
            max-width: 44px;
            min-height: 44px;
            max-height: 44px;
        }

        QPushButton#discordButton:hover {
            background-color: transparent;
            border: none;
        }

        QPushButton#discordButton:pressed {
            background-color: transparent;
            border: none;
        }

        /* Group Boxes */
        QGroupBox {
            color: #d0d0d0;
            border: 1px solid #3a3a3a;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 12px;
            font-weight: 600;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px 0 3px;
        }

        /* Tabs */
        QTabWidget::pane {
            border: 1px solid #3a3a3a;
            background-color: #1a1a1a;
        }

        QTabBar::tab {
            background-color: #262626;
            color: #a0a0a0;
            padding: 6px 20px;
            border: none;
            margin-right: 2px;
        }

        QTabBar::tab:selected {
            background-color: #2a2a2a;
            color: #d0d0d0;
            border-bottom: 2px solid #d65d3e;
        }

        QTabBar::tab:hover {
            background-color: #2f2f2f;
            color: #d0d0d0;
        }

        /* Progress Bar */
        QProgressBar {
            background-color: #1f1f1f;
            color: #d0d0d0;
            border: 1px solid #3a3a3a;
            border-radius: 3px;
            text-align: center;
            height: 20px;
        }

        QProgressBar::chunk {
            background-color: #4a9c9c;
            border-radius: 2px;
        }

        /* Scroll Bars */
        QScrollBar:vertical {
            background-color: #1a1a1a;
            width: 12px;
            border: none;
        }

        QScrollBar::handle:vertical {
            background-color: #4a4a4a;
            border-radius: 6px;
            min-height: 20px;
            margin: 2px;
        }

        QScrollBar::handle:vertical:hover {
            background-color: #5a5a5a;
        }

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            border: none;
            background: none;
            height: 0px;
        }

        QScrollBar:horizontal {
            background-color: #1a1a1a;
            height: 12px;
            border: none;
        }

        QScrollBar::handle:horizontal {
            background-color: #4a4a4a;
            border-radius: 6px;
            min-width: 20px;
            margin: 2px;
        }

        QScrollBar::handle:horizontal:hover {
            background-color: #5a5a5a;
        }

        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            border: none;
            background: none;
            width: 0px;
        }

        /* Scroll Area */
        QScrollArea {
            background-color: #1a1a1a;
            border: none;
        }

        /* Message Boxes */
        QMessageBox {
            background-color: #1a1a1a;
        }

        QMessageBox QLabel {
            color: #d0d0d0;
        }

        QMessageBox QPushButton {
            min-width: 60px;
        }

        /* File Dialog */
        QFileDialog {
            background-color: #1a1a1a;
            color: #d0d0d0;
        }
        """
        self.setStyleSheet(stylesheet)

    def _t(self, text: str, **kwargs: object) -> str:
        return self._localizer.t(text, **kwargs)
