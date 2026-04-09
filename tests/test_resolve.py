from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.resolve import (
    MEDIA_POOL_MUSIC_FOLDER_NAME,
    MockResolveAdapter,
    PreviewRenderRequest,
    RealResolveAdapter,
    ResolveAdapterError,
    _match_render_format_name,
)


class _SettingsAwareProject:
    def __init__(self, accepts_settings) -> None:
        self.accepts_settings = accepts_settings
        self.attempts: list[dict[str, object]] = []

    def SetRenderSettings(self, settings: dict[str, object]) -> bool:
        copied = dict(settings)
        self.attempts.append(copied)
        return bool(self.accepts_settings(copied))


class _PageRestoreHandle:
    def __init__(self, open_page_result: bool) -> None:
        self.open_page_result = open_page_result
        self.calls: list[str] = []

    def OpenPage(self, page_name: str) -> bool:
        self.calls.append(page_name)
        return self.open_page_result


class _MediaPoolFolder:
    def __init__(self, name: str, children: list["_MediaPoolFolder"] | None = None) -> None:
        self._name = name
        self._children = children or []

    def GetName(self) -> str:
        return self._name

    def GetSubFolderList(self) -> list["_MediaPoolFolder"]:
        return list(self._children)


class _MediaPoolStub:
    def __init__(self, root_folder: _MediaPoolFolder) -> None:
        self._root_folder = root_folder
        self._current_folder = root_folder

    def GetRootFolder(self) -> _MediaPoolFolder:
        return self._root_folder

    def GetCurrentFolder(self) -> _MediaPoolFolder:
        return self._current_folder

    def SetCurrentFolder(self, folder: _MediaPoolFolder) -> bool:
        self._current_folder = folder
        return True

    def AddSubFolder(self, parent: _MediaPoolFolder, name: str) -> _MediaPoolFolder:
        created = _MediaPoolFolder(name)
        parent._children.append(created)
        return created


class ResolveAdapterTests(unittest.TestCase):
    def test_mock_resolve_adapter_describes_dev_mode(self) -> None:
        adapter = MockResolveAdapter()

        self.assertFalse(adapter.is_available())
        self.assertIn("mock adapter", adapter.get_environment_summary().lower())
        context = adapter.get_current_timeline_context()
        self.assertEqual(context.project_name, "Mock Project")
        self.assertEqual(context.marker_count, 3)

    def test_mock_resolve_adapter_queues_preview_render(self) -> None:
        adapter = MockResolveAdapter()
        with TemporaryDirectory() as temp_dir:
            request = PreviewRenderRequest(
                target_dir=temp_dir,
                custom_name="sample-preview",
                frame_rate=24.0,
            )

            job = adapter.queue_preview_render(request)
            started = adapter.start_render_job(job.job_id)
            status = adapter.get_render_job_status(job.job_id)
            finished = adapter.get_render_job_status(job.job_id)

            self.assertEqual(job.target_path, str(Path(temp_dir) / "sample-preview.mp4"))
            self.assertTrue(Path(job.target_path).exists())

        self.assertEqual(started.status, "Rendering")
        self.assertEqual(status.status, "Rendering")
        self.assertEqual(finished.status, "Complete")

    def test_real_resolve_adapter_exposes_handle(self) -> None:
        handle = object()
        adapter = RealResolveAdapter(handle)

        self.assertTrue(adapter.is_available())
        self.assertIs(adapter.raw_handle(), handle)

    def test_match_render_format_name_is_case_insensitive(self) -> None:
        self.assertEqual(_match_render_format_name({"MP4": "MP4", "QuickTime": "QuickTime"}, "mp4"), "MP4")

    def test_apply_preview_render_settings_falls_back_when_full_profile_is_rejected(self) -> None:
        request = PreviewRenderRequest(
            target_dir="C:/temp",
            custom_name="preview",
            frame_rate=23.976,
        )

        def accepts(settings: dict[str, object]) -> bool:
            required = {"SelectAllFrames", "TargetDir", "CustomName", "FormatWidth", "FormatHeight"}
            return required.issubset(settings.keys()) and "FrameRate" not in settings

        project = _SettingsAwareProject(accepts)
        adapter = RealResolveAdapter(object())

        adapter._apply_preview_render_settings(project, request)

        self.assertGreaterEqual(len(project.attempts), 2)
        self.assertTrue(any("FrameRate" not in attempt for attempt in project.attempts))

    def test_apply_preview_render_settings_tries_alternative_resolution_keys(self) -> None:
        request = PreviewRenderRequest(
            target_dir="C:/temp",
            custom_name="preview",
            frame_rate=24.0,
        )

        def accepts(settings: dict[str, object]) -> bool:
            required = {"SelectAllFrames", "TargetDir", "CustomName", "ResolutionWidth", "ResolutionHeight"}
            return required.issubset(settings.keys()) and "FormatWidth" not in settings and "FrameRate" not in settings

        project = _SettingsAwareProject(accepts)
        adapter = RealResolveAdapter(object())

        adapter._apply_preview_render_settings(project, request)

        self.assertTrue(any("ResolutionWidth" in attempt for attempt in project.attempts))

    def test_apply_preview_render_settings_raises_when_no_profile_is_supported(self) -> None:
        request = PreviewRenderRequest(
            target_dir="C:/temp",
            custom_name="preview",
            frame_rate=24.0,
        )
        project = _SettingsAwareProject(lambda _settings: False)
        adapter = RealResolveAdapter(object())

        with self.assertRaises(ResolveAdapterError):
            adapter._apply_preview_render_settings(project, request)

    def test_restore_previous_page_is_best_effort(self) -> None:
        handle = _PageRestoreHandle(open_page_result=False)
        adapter = RealResolveAdapter(handle)

        adapter._restore_previous_page("edit")

        self.assertEqual(handle.calls, ["edit"])

    def test_ensure_media_pool_music_folder_reuses_existing_folder(self) -> None:
        existing = _MediaPoolFolder(MEDIA_POOL_MUSIC_FOLDER_NAME)
        root = _MediaPoolFolder("Root", children=[existing])
        media_pool = _MediaPoolStub(root)
        adapter = RealResolveAdapter(object())

        resolved_folder, folder_name = adapter._ensure_media_pool_music_folder(media_pool)

        self.assertIs(resolved_folder, existing)
        self.assertEqual(folder_name, MEDIA_POOL_MUSIC_FOLDER_NAME)

    def test_ensure_media_pool_music_folder_creates_folder_when_missing(self) -> None:
        root = _MediaPoolFolder("Root")
        media_pool = _MediaPoolStub(root)
        adapter = RealResolveAdapter(object())

        resolved_folder, folder_name = adapter._ensure_media_pool_music_folder(media_pool)

        self.assertIsNotNone(resolved_folder)
        self.assertEqual(resolved_folder.GetName(), MEDIA_POOL_MUSIC_FOLDER_NAME)
        self.assertEqual(folder_name, MEDIA_POOL_MUSIC_FOLDER_NAME)
        self.assertEqual(len(root.GetSubFolderList()), 1)
