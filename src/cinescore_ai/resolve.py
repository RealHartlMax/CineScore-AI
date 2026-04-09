from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ResolveAdapterError(RuntimeError):
    pass


MEDIA_POOL_MUSIC_FOLDER_NAME = "CineScore AI Music"


@dataclass(slots=True)
class ResolveMarker:
    frame_offset: int
    absolute_frame: int
    relative_seconds: float
    timestamp: str
    duration_frames: int
    color: str
    name: str
    note: str
    keywords: tuple[str, ...] = ()
    custom_data: str = ""


@dataclass(slots=True)
class ResolveTimelineContext:
    project_name: str
    timeline_name: str
    timeline_id: str
    frame_rate: float
    start_frame: int
    end_frame: int
    start_timecode: str
    video_track_count: int
    audio_track_count: int
    markers: list[ResolveMarker] = field(default_factory=list)

    @property
    def marker_count(self) -> int:
        return len(self.markers)

    @property
    def duration_frames(self) -> int:
        return max(0, self.end_frame - self.start_frame)

    @property
    def duration_seconds(self) -> float:
        if self.frame_rate <= 0:
            return 0.0
        return self.duration_frames / self.frame_rate


@dataclass(slots=True)
class PreviewRenderPreset:
    width: int = 1280
    height: int = 720
    render_format: str = "mp4"
    file_extension: str = "mp4"
    codec: str = "H264"
    audio_codec: str = "aac"
    video_quality: str | int = "Low"
    export_video: bool = True
    export_audio: bool = True
    network_optimization: bool = True


@dataclass(slots=True)
class PreviewRenderRequest:
    target_dir: str
    custom_name: str
    frame_rate: float
    preset: PreviewRenderPreset = field(default_factory=PreviewRenderPreset)

    @property
    def target_path(self) -> str:
        return str(Path(self.target_dir) / f"{self.custom_name}.{self.preset.file_extension}")


@dataclass(slots=True)
class PreviewRenderJob:
    job_id: str
    target_dir: str
    custom_name: str
    target_path: str
    render_format: str
    codec: str
    width: int
    height: int
    status: str


@dataclass(slots=True)
class RenderJobStatus:
    job_id: str
    status: str
    completion_percentage: float | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ImportedAudioPlacement:
    file_path: str
    track_index: int
    record_frame: int
    media_pool_folder_name: str | None = None
    media_pool_item_name: str | None = None
    timeline_item_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class ResolveAdapter(ABC):
    @property
    @abstractmethod
    def runtime_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_environment_summary(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def raw_handle(self) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def get_current_timeline_context(self) -> ResolveTimelineContext:
        raise NotImplementedError

    @abstractmethod
    def queue_preview_render(self, request: PreviewRenderRequest) -> PreviewRenderJob:
        raise NotImplementedError

    @abstractmethod
    def start_render_job(self, job_id: str) -> RenderJobStatus:
        raise NotImplementedError

    @abstractmethod
    def get_render_job_status(self, job_id: str) -> RenderJobStatus:
        raise NotImplementedError

    @abstractmethod
    def ensure_audio_track(self, track_index: int | None = None, audio_type: str = "stereo") -> int:
        raise NotImplementedError

    @abstractmethod
    def place_audio_clip(
        self,
        file_path: str,
        record_frame: int,
        track_index: int,
        timeline_context: ResolveTimelineContext | None = None,
    ) -> ImportedAudioPlacement:
        raise NotImplementedError


class MockResolveAdapter(ResolveAdapter):
    def __init__(self) -> None:
        self._mock_context = ResolveTimelineContext(
            project_name="Mock Project",
            timeline_name="Assembly Cut",
            timeline_id="mock-timeline-001",
            frame_rate=24.0,
            start_frame=86400,
            end_frame=86400 + 720,
            start_timecode="01:00:00:00",
            video_track_count=2,
            audio_track_count=3,
            markers=[
                ResolveMarker(
                    frame_offset=48,
                    absolute_frame=86448,
                    relative_seconds=2.0,
                    timestamp="00:00:02.000",
                    duration_frames=24,
                    color="Blue",
                    name="Intro",
                    note="Open on a calm, curious texture.",
                ),
                ResolveMarker(
                    frame_offset=240,
                    absolute_frame=86640,
                    relative_seconds=10.0,
                    timestamp="00:00:10.000",
                    duration_frames=48,
                    color="Green",
                    name="Lift",
                    note="Build into a more cinematic groove here.",
                ),
                ResolveMarker(
                    frame_offset=480,
                    absolute_frame=86880,
                    relative_seconds=20.0,
                    timestamp="00:00:20.000",
                    duration_frames=24,
                    color="Red",
                    name="Drop",
                    note="Hit the reveal with a bigger percussion accent.",
                ),
            ],
        )
        self._queued_jobs: dict[str, PreviewRenderJob] = {}
        self._job_poll_counts: dict[str, int] = {}
        self._placed_audio: list[ImportedAudioPlacement] = []

    @property
    def runtime_name(self) -> str:
        return "Development Mode"

    def is_available(self) -> bool:
        return False

    def get_environment_summary(self) -> str:
        return "Running outside DaVinci Resolve using the mock adapter."

    def raw_handle(self) -> Any | None:
        return None

    def get_current_timeline_context(self) -> ResolveTimelineContext:
        return self._mock_context

    def queue_preview_render(self, request: PreviewRenderRequest) -> PreviewRenderJob:
        job_id = f"mock-render-job-{len(self._queued_jobs) + 1:03d}"
        job = PreviewRenderJob(
            job_id=job_id,
            target_dir=request.target_dir,
            custom_name=request.custom_name,
            target_path=request.target_path,
            render_format=request.preset.render_format,
            codec=request.preset.codec,
            width=request.preset.width,
            height=request.preset.height,
            status="Queued",
        )
        self._queued_jobs[job_id] = job
        self._job_poll_counts[job_id] = 0
        return job

    def start_render_job(self, job_id: str) -> RenderJobStatus:
        job = self._queued_jobs.get(job_id)
        if job is None:
            raise ResolveAdapterError(f"Unknown mock render job '{job_id}'.")
        job.status = "Rendering"
        self._job_poll_counts[job_id] = 0
        return RenderJobStatus(
            job_id=job.job_id,
            status=job.status,
            completion_percentage=0.0,
            raw={"JobStatus": job.status, "CompletionPercentage": 0.0},
        )

    def get_render_job_status(self, job_id: str) -> RenderJobStatus:
        job = self._queued_jobs.get(job_id)
        if job is None:
            raise ResolveAdapterError(f"Unknown mock render job '{job_id}'.")
        completion_percentage = 0.0
        if job.status == "Rendering":
            poll_count = self._job_poll_counts.get(job_id, 0) + 1
            self._job_poll_counts[job_id] = poll_count
            completion_percentage = min(100.0, float(poll_count * 50))
            if completion_percentage >= 100.0:
                job.status = "Complete"
                Path(job.target_dir).mkdir(parents=True, exist_ok=True)
                Path(job.target_path).write_text("mock preview render output\n", encoding="utf-8")
        elif job.status == "Complete":
            completion_percentage = 100.0
        return RenderJobStatus(
            job_id=job.job_id,
            status=job.status,
            completion_percentage=completion_percentage,
            raw={"JobStatus": job.status, "CompletionPercentage": completion_percentage},
        )

    def ensure_audio_track(self, track_index: int | None = None, audio_type: str = "stereo") -> int:
        desired_track = track_index or (self._mock_context.audio_track_count + 1)
        if desired_track > self._mock_context.audio_track_count:
            self._mock_context.audio_track_count = desired_track
        return desired_track

    def place_audio_clip(
        self,
        file_path: str,
        record_frame: int,
        track_index: int,
        timeline_context: ResolveTimelineContext | None = None,
    ) -> ImportedAudioPlacement:
        audio_path = Path(file_path)
        if not audio_path.exists():
            raise ResolveAdapterError(f"Audio file does not exist: {audio_path}")
        resolved_track = self.ensure_audio_track(track_index=track_index)
        placement = ImportedAudioPlacement(
            file_path=str(audio_path),
            track_index=resolved_track,
            record_frame=int(record_frame),
            media_pool_folder_name=_build_media_pool_folder_path(timeline_context),
            media_pool_item_name=audio_path.name,
            timeline_item_name=audio_path.stem,
            raw={"mock": True},
        )
        self._placed_audio.append(placement)
        return placement


class RealResolveAdapter(ResolveAdapter):
    def __init__(self, resolve_handle: Any) -> None:
        self._resolve_handle = resolve_handle

    @property
    def runtime_name(self) -> str:
        return "DaVinci Resolve"

    def is_available(self) -> bool:
        return self._resolve_handle is not None

    def get_environment_summary(self) -> str:
        if self.is_available():
            return "Connected to the DaVinci Resolve scripting runtime."
        return "Resolve scripting handle is missing."

    def raw_handle(self) -> Any | None:
        return self._resolve_handle

    def get_current_timeline_context(self) -> ResolveTimelineContext:
        project = self._require_current_project()
        timeline = self._require_current_timeline(project)

        start_frame = int(timeline.GetStartFrame())
        end_frame = int(timeline.GetEndFrame())
        frame_rate = self._read_frame_rate(timeline, project)
        markers = self._extract_markers(
            raw_markers=timeline.GetMarkers() or {},
            start_frame=start_frame,
            frame_rate=frame_rate,
        )

        timeline_id_getter = getattr(timeline, "GetUniqueId", None)
        timeline_id = str(timeline_id_getter()) if callable(timeline_id_getter) else timeline.GetName()

        return ResolveTimelineContext(
            project_name=str(project.GetName()),
            timeline_name=str(timeline.GetName()),
            timeline_id=timeline_id,
            frame_rate=frame_rate,
            start_frame=start_frame,
            end_frame=end_frame,
            start_timecode=str(timeline.GetStartTimecode()),
            video_track_count=int(timeline.GetTrackCount("video")),
            audio_track_count=int(timeline.GetTrackCount("audio")),
            markers=markers,
        )

    def queue_preview_render(self, request: PreviewRenderRequest) -> PreviewRenderJob:
        project = self._require_current_project()
        self._require_current_timeline(project)
        Path(request.target_dir).mkdir(parents=True, exist_ok=True)

        previous_page = self._safe_call(self._resolve_handle, "GetCurrentPage")
        previous_format = self._safe_call(project, "GetCurrentRenderFormatAndCodec") or {}
        previous_mode = self._safe_call(project, "GetCurrentRenderMode")

        try:
            self._open_page("deliver")
            self._set_single_clip_render_mode(project)
            self._set_render_format_and_codec(project, request)
            self._apply_preview_render_settings(project, request)
            job_id = project.AddRenderJob()
            if not job_id:
                raise ResolveAdapterError("Resolve did not return a render job id.")
        finally:
            self._restore_render_mode(project, previous_mode)
            self._restore_render_format_and_codec(project, previous_format)
            self._restore_previous_page(previous_page)

        return PreviewRenderJob(
            job_id=str(job_id),
            target_dir=request.target_dir,
            custom_name=request.custom_name,
            target_path=request.target_path,
            render_format=request.preset.render_format,
            codec=request.preset.codec,
            width=request.preset.width,
            height=request.preset.height,
            status="Queued",
        )

    def start_render_job(self, job_id: str) -> RenderJobStatus:
        project = self._require_current_project()
        previous_page = self._safe_call(self._resolve_handle, "GetCurrentPage")
        try:
            self._open_page("deliver")
            started = self._try_start_rendering(project, job_id)
            if not started:
                raise ResolveAdapterError(f"Resolve failed to start render job '{job_id}'.")
        finally:
            self._restore_previous_page(previous_page)
        return self.get_render_job_status(job_id)

    def get_render_job_status(self, job_id: str) -> RenderJobStatus:
        project = self._require_current_project()
        raw_status = project.GetRenderJobStatus(job_id)
        if not isinstance(raw_status, dict):
            raise ResolveAdapterError(f"Resolve returned no status for render job '{job_id}'.")

        completion = raw_status.get("CompletionPercentage")
        if completion is None:
            completion = raw_status.get("completionPercentage")
        try:
            completion_value = float(completion) if completion is not None else None
        except (TypeError, ValueError):
            completion_value = None

        status = raw_status.get("JobStatus") or raw_status.get("Status") or "Unknown"
        return RenderJobStatus(
            job_id=job_id,
            status=str(status),
            completion_percentage=completion_value,
            raw=raw_status,
        )

    def ensure_audio_track(self, track_index: int | None = None, audio_type: str = "stereo") -> int:
        project = self._require_current_project()
        timeline = self._require_current_timeline(project)
        current_count = int(timeline.GetTrackCount("audio"))
        desired_track = track_index or (current_count + 1)

        while current_count < desired_track:
            added = self._try_add_audio_track(timeline, current_count + 1, audio_type)
            if not added:
                raise ResolveAdapterError(f"Resolve could not add audio track {current_count + 1}.")
            current_count = int(timeline.GetTrackCount("audio"))

        return desired_track

    def place_audio_clip(
        self,
        file_path: str,
        record_frame: int,
        track_index: int,
        timeline_context: ResolveTimelineContext | None = None,
    ) -> ImportedAudioPlacement:
        project = self._require_current_project()
        self._require_current_timeline(project)
        media_pool = project.GetMediaPool()
        if media_pool is None:
            raise ResolveAdapterError("Resolve did not return a media pool handle.")

        resolved_track = self.ensure_audio_track(track_index=track_index)
        previous_folder = self._safe_call(media_pool, "GetCurrentFolder")
        target_folder, target_folder_name = self._ensure_media_pool_music_folder(media_pool, timeline_context)
        if target_folder is not None:
            self._safe_call(media_pool, "SetCurrentFolder", target_folder)
        try:
            imported_item = self._import_media_item(project, media_pool, file_path)
        finally:
            if previous_folder is not None:
                self._safe_call(media_pool, "SetCurrentFolder", previous_folder)
        appended_items = media_pool.AppendToTimeline(
            [
                {
                    "mediaPoolItem": imported_item,
                    "mediaType": 2,
                    "trackIndex": int(resolved_track),
                    "recordFrame": int(record_frame),
                }
            ]
        )
        if not appended_items:
            raise ResolveAdapterError(f"Resolve could not append audio clip '{file_path}' to the timeline.")

        timeline_item = appended_items[0] if isinstance(appended_items, list) else appended_items
        return ImportedAudioPlacement(
            file_path=str(file_path),
            track_index=int(resolved_track),
            record_frame=int(record_frame),
            media_pool_folder_name=target_folder_name,
            media_pool_item_name=self._safe_name(imported_item),
            timeline_item_name=self._safe_name(timeline_item),
            raw={
                "appended_items": appended_items,
                "media_pool_folder_name": target_folder_name,
            },
        )

    def _require_current_project(self) -> Any:
        if not self.is_available():
            raise ResolveAdapterError("Resolve scripting handle is not available.")
        project_manager = self._resolve_handle.GetProjectManager()
        if project_manager is None:
            raise ResolveAdapterError("Unable to access the Resolve project manager.")
        project = project_manager.GetCurrentProject()
        if project is None:
            raise ResolveAdapterError("No current Resolve project is open.")
        return project

    def _require_current_timeline(self, project: Any) -> Any:
        timeline = project.GetCurrentTimeline()
        if timeline is None:
            raise ResolveAdapterError("The current project has no active timeline.")
        return timeline

    def _import_media_item(self, project: Any, media_pool: Any, file_path: str) -> Any:
        from pathlib import Path
        import time
        
        file_obj = Path(file_path)
        
        # Verify file exists before attempting import
        if not file_obj.exists():
            raise ResolveAdapterError(
                f"Audio file does not exist and cannot be imported: {file_path}"
            )
        
        # Attempt imports with retry logic
        max_attempts = 3
        for attempt in range(max_attempts):
            import_result = None
            
            # Try method 1: media_pool.ImportMedia()
            import_media = getattr(media_pool, "ImportMedia", None)
            if callable(import_media):
                try:
                    import_result = import_media([file_path])
                except Exception as e:
                    if attempt < max_attempts - 1:
                        time.sleep(0.1)
                        continue
                    raise ResolveAdapterError(
                        f"Resolve ImportMedia() raised exception for '{file_path}': {e}"
                    )
            
            # If first method failed, try method 2: media_storage.AddItemListToMediaPool()
            if not import_result:
                try:
                    media_storage = self._safe_call(self._resolve_handle, "GetMediaStorage")
                    add_to_pool = (
                        getattr(media_storage, "AddItemListToMediaPool", None)
                        if media_storage is not None
                        else None
                    )
                    if callable(add_to_pool):
                        import_result = add_to_pool([file_path])
                except Exception as e:
                    if attempt < max_attempts - 1:
                        time.sleep(0.1)
                        continue
                    raise ResolveAdapterError(
                        f"Resolve AddItemListToMediaPool() raised exception for '{file_path}': {e}"
                    )
            
            # If we got a result, process it
            if import_result:
                if isinstance(import_result, list):
                    if not import_result:
                        if attempt < max_attempts - 1:
                            time.sleep(0.1)
                            continue
                        raise ResolveAdapterError(
                            f"Resolve returned empty list for '{file_path}'."
                        )
                    return import_result[0]
                return import_result
            
            # If no result and more attempts available, wait and retry
            if attempt < max_attempts - 1:
                time.sleep(0.1)
        
        # All attempts failed
        raise ResolveAdapterError(
            f"Resolve could not import audio file '{file_path}' into the media pool "
            f"after {max_attempts} attempt(s). File exists at {file_obj.absolute()}"
        )

    def _ensure_media_pool_music_folder(
        self,
        media_pool: Any,
        timeline_context: ResolveTimelineContext | None = None,
    ) -> tuple[Any | None, str | None]:
        root_folder = self._safe_call(media_pool, "GetRootFolder")
        if root_folder is None:
            root_folder = self._safe_call(media_pool, "GetCurrentFolder")
        if root_folder is None:
            return None, None

        existing_folder = self._find_subfolder_by_name(root_folder, MEDIA_POOL_MUSIC_FOLDER_NAME)
        if existing_folder is not None:
            target_folder = existing_folder
        else:
            created_folder = self._try_add_subfolder(media_pool, root_folder, MEDIA_POOL_MUSIC_FOLDER_NAME)
            target_folder = created_folder or self._find_subfolder_by_name(root_folder, MEDIA_POOL_MUSIC_FOLDER_NAME)

        if target_folder is None:
            return None, None

        folder_names = [MEDIA_POOL_MUSIC_FOLDER_NAME]
        for nested_folder_name in _build_media_pool_folder_names(timeline_context):
            nested_folder = self._find_subfolder_by_name(target_folder, nested_folder_name)
            if nested_folder is None:
                nested_folder = self._try_add_subfolder(media_pool, target_folder, nested_folder_name)
            if nested_folder is None:
                nested_folder = self._find_subfolder_by_name(target_folder, nested_folder_name)
            if nested_folder is None:
                break
            target_folder = nested_folder
            folder_names.append(nested_folder_name)

        return target_folder, " / ".join(folder_names)

    def _find_subfolder_by_name(self, parent_folder: Any, folder_name: str) -> Any | None:
        for method_name in ("GetSubFolderList", "GetSubFolders"):
            subfolders = self._safe_call(parent_folder, method_name)
            for folder in self._iter_folder_candidates(subfolders):
                if self._safe_name(folder) == folder_name:
                    return folder
        return None

    def _iter_folder_candidates(self, subfolders: Any) -> list[Any]:
        if isinstance(subfolders, dict):
            return [folder for folder in subfolders.values() if folder is not None]
        if isinstance(subfolders, list):
            return [folder for folder in subfolders if folder is not None]
        return []

    def _try_add_subfolder(self, media_pool: Any, parent_folder: Any, folder_name: str) -> Any | None:
        attempts: list[tuple[Any, ...]] = [
            (parent_folder, folder_name),
            (folder_name, parent_folder),
            (folder_name,),
        ]
        add_subfolder = getattr(media_pool, "AddSubFolder", None)
        if callable(add_subfolder):
            for args in attempts:
                try:
                    created = add_subfolder(*args)
                except TypeError:
                    continue
                except Exception:
                    continue
                if created:
                    return created

        folder_add_subfolder = getattr(parent_folder, "AddSubFolder", None)
        if callable(folder_add_subfolder):
            for args in ((folder_name,),):
                try:
                    created = folder_add_subfolder(*args)
                except TypeError:
                    continue
                except Exception:
                    continue
                if created:
                    return created
        return None

    def _read_frame_rate(self, timeline: Any, project: Any) -> float:
        for owner in (timeline, project):
            try:
                value = owner.GetSetting("timelineFrameRate")
            except Exception:
                value = None
            parsed = _coerce_frame_rate(value)
            if parsed is not None:
                return parsed
        return 24.0

    def _extract_markers(
        self,
        raw_markers: dict[Any, Any],
        start_frame: int,
        frame_rate: float,
    ) -> list[ResolveMarker]:
        markers: list[ResolveMarker] = []
        for raw_frame_id, payload in sorted(raw_markers.items(), key=lambda item: float(item[0])):
            marker_payload = payload if isinstance(payload, dict) else {}
            frame_offset = int(float(raw_frame_id))
            duration_frames = int(float(marker_payload.get("duration", 0) or 0))
            markers.append(
                ResolveMarker(
                    frame_offset=frame_offset,
                    absolute_frame=start_frame + frame_offset,
                    relative_seconds=(frame_offset / frame_rate) if frame_rate > 0 else 0.0,
                    timestamp=_format_relative_timestamp(frame_offset, frame_rate),
                    duration_frames=duration_frames,
                    color=str(marker_payload.get("color", "")),
                    name=str(marker_payload.get("name", "")),
                    note=str(marker_payload.get("note", "")),
                    keywords=_extract_marker_keywords(marker_payload),
                    custom_data=str(marker_payload.get("customData", "")),
                )
            )
        return markers

    def _open_page(self, page_name: str) -> None:
        if not self._resolve_handle.OpenPage(page_name):
            raise ResolveAdapterError(f"Resolve could not switch to the '{page_name}' page.")

    def _set_single_clip_render_mode(self, project: Any) -> None:
        if not project.SetCurrentRenderMode(1):
            raise ResolveAdapterError("Resolve could not switch render mode to single clip.")

    def _set_render_format_and_codec(self, project: Any, request: PreviewRenderRequest) -> None:
        formats = project.GetRenderFormats() or {}
        format_name = _match_render_format_name(formats, request.preset.render_format)
        if format_name is None:
            available = ", ".join(sorted(str(key) for key in formats.keys()))
            raise ResolveAdapterError(
                f"Render format '{request.preset.render_format}' is unavailable. Available formats: {available}"
            )

        codecs = project.GetRenderCodecs(format_name) or {}
        codec_name = _match_codec_name(codecs, request.preset.codec)
        if codec_name is None:
            available = ", ".join(sorted(str(value) for value in codecs.values()))
            raise ResolveAdapterError(
                f"Render codec '{request.preset.codec}' is unavailable for format '{format_name}'. "
                f"Available codecs: {available}"
            )

        if not project.SetCurrentRenderFormatAndCodec(format_name, codec_name):
            raise ResolveAdapterError(
                f"Resolve could not set render format '{format_name}' and codec '{codec_name}'."
            )

    def _apply_preview_render_settings(self, project: Any, request: PreviewRenderRequest) -> None:
        base_settings = {
            "SelectAllFrames": True,
            "TargetDir": request.target_dir,
            "CustomName": request.custom_name,
            "ExportVideo": request.preset.export_video,
            "ExportAudio": request.preset.export_audio,
        }

        optional_settings = {
            "FrameRate": request.frame_rate,
            "VideoQuality": request.preset.video_quality,
            "AudioCodec": request.preset.audio_codec,
            "NetworkOptimization": request.preset.network_optimization,
        }

        resolution_variants: list[dict[str, Any]] = [
            {
                "FormatWidth": request.preset.width,
                "FormatHeight": request.preset.height,
            },
            {
                "ResolutionWidth": request.preset.width,
                "ResolutionHeight": request.preset.height,
            },
        ]

        candidate_settings: list[dict[str, Any]] = []
        for resolution_settings in resolution_variants:
            candidate_settings.append({**base_settings, **resolution_settings, **optional_settings})
            candidate_settings.append(
                {
                    **base_settings,
                    **resolution_settings,
                    "VideoQuality": request.preset.video_quality,
                    "AudioCodec": request.preset.audio_codec,
                    "NetworkOptimization": request.preset.network_optimization,
                }
            )
            candidate_settings.append({**base_settings, **resolution_settings})

        for settings in candidate_settings:
            if project.SetRenderSettings(settings):
                return

        raise ResolveAdapterError("Resolve rejected the preview render settings.")

    def _restore_render_mode(self, project: Any, previous_mode: Any) -> None:
        if previous_mode in (0, 1):
            self._safe_call(project, "SetCurrentRenderMode", previous_mode)

    def _restore_render_format_and_codec(self, project: Any, previous_format: Any) -> None:
        if not isinstance(previous_format, dict):
            return
        render_format = previous_format.get("format")
        codec = previous_format.get("codec")
        if render_format and codec:
            self._safe_call(project, "SetCurrentRenderFormatAndCodec", render_format, codec)

    def _restore_previous_page(self, previous_page: Any) -> None:
        if not previous_page or str(previous_page) == "deliver":
            return
        self._safe_call(self._resolve_handle, "OpenPage", str(previous_page))

    def _safe_call(self, target: Any, method_name: str, *args: Any) -> Any | None:
        method = getattr(target, method_name, None)
        if not callable(method):
            return None
        try:
            return method(*args)
        except Exception:
            return None

    def _try_add_audio_track(self, timeline: Any, track_index: int, audio_type: str) -> bool:
        attempts: list[tuple[Any, ...]] = [
            ("audio",),
            ("audio", audio_type),
            ("audio", {"audioType": audio_type}),
            ("audio", {"audioType": audio_type, "index": track_index}),
        ]
        for args in attempts:
            try:
                added = timeline.AddTrack(*args)
            except TypeError:
                continue
            except Exception:
                continue
            if added:
                return True
        return False

    def _safe_name(self, item: Any) -> str | None:
        getter = getattr(item, "GetName", None)
        if callable(getter):
            try:
                name = getter()
            except Exception:
                return None
            if name is not None:
                return str(name)
        return None

    def _try_start_rendering(self, project: Any, job_id: str) -> bool:
        attempts: list[tuple[Any, ...]] = [
            (job_id,),
            ([job_id], False),
            ([job_id],),
        ]
        for args in attempts:
            try:
                started = project.StartRendering(*args)
            except TypeError:
                continue
            except Exception as exc:
                raise ResolveAdapterError(f"Resolve raised an error while starting render job '{job_id}': {exc}") from exc
            if started:
                return True
        return False


def _coerce_frame_rate(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _format_relative_timestamp(frame_offset: int, frame_rate: float) -> str:
    if frame_rate <= 0:
        return "00:00:00.000"

    total_seconds = frame_offset / frame_rate
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int(round((total_seconds - int(total_seconds)) * 1000))
    if milliseconds == 1000:
        milliseconds = 0
        seconds += 1
    if seconds == 60:
        seconds = 0
        minutes += 1
    if minutes == 60:
        minutes = 0
        hours += 1
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _extract_marker_keywords(marker_payload: dict[Any, Any]) -> tuple[str, ...]:
    for key in ("keywords", "keyword", "tags", "tag"):
        value = marker_payload.get(key)
        extracted = _normalize_marker_keywords(value)
        if extracted:
            return extracted
    return ()


def _normalize_marker_keywords(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = value.replace(";", ",").replace("\n", ",").split(",")
        cleaned = tuple(part.strip() for part in parts if part and part.strip())
        return cleaned
    if isinstance(value, (list, tuple, set)):
        cleaned = tuple(str(part).strip() for part in value if str(part).strip())
        return cleaned
    return ()


def _build_media_pool_folder_names(timeline_context: ResolveTimelineContext | None) -> list[str]:
    if timeline_context is None:
        return []

    folder_names: list[str] = []
    for value in (timeline_context.project_name, timeline_context.timeline_name):
        cleaned = _sanitize_media_pool_folder_name(value)
        if cleaned:
            folder_names.append(cleaned)
    return folder_names


def _build_media_pool_folder_path(timeline_context: ResolveTimelineContext | None) -> str:
    return " / ".join([MEDIA_POOL_MUSIC_FOLDER_NAME, *_build_media_pool_folder_names(timeline_context)])


def _sanitize_media_pool_folder_name(value: str) -> str:
    sanitized = " ".join(str(value).split()).strip()
    for char in '/\\:*?"<>|':
        sanitized = sanitized.replace(char, "-")
    sanitized = sanitized.strip(" .")
    return sanitized or "Untitled"


def _match_codec_name(codecs: dict[Any, Any], preferred_codec: str) -> str | None:
    preferred = preferred_codec.strip().lower()
    for candidate in codecs.values():
        candidate_text = str(candidate)
        if candidate_text.lower() == preferred:
            return candidate_text
    for key, candidate in codecs.items():
        if str(key).strip().lower() == preferred:
            return str(candidate)
    return None


def _match_render_format_name(formats: dict[Any, Any], preferred_format: str) -> str | None:
    preferred = preferred_format.strip().lower()
    for key in formats.keys():
        key_text = str(key).strip()
        if key_text.lower() == preferred:
            return key_text
    for key, value in formats.items():
        value_text = str(value).strip()
        if value_text.lower() == preferred:
            return str(key).strip()
    return None
