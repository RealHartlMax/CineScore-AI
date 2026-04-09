from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from cinescore_ai.marker_directives import MarkerMusicDirective
from cinescore_ai.resolve import ResolveAdapter


class FrameExtractionError(RuntimeError):
    pass


@dataclass(slots=True)
class ExtractedMarkerFrame:
    marker_timestamp: str
    marker_name: str
    image_path: str
    mime_type: str = "image/jpeg"
    export_method: str = ""


class PreviewFrameExtractor:
    def __init__(self, resolve_adapter: ResolveAdapter | None = None) -> None:
        self._resolve_adapter = resolve_adapter

    def extract_marker_frames(
        self,
        directives: list[MarkerMusicDirective],
        output_directory: str | Path,
        max_images: int = 10,
    ) -> list[ExtractedMarkerFrame]:
        selected = [directive for directive in directives if directive.use_image][: max(0, max_images)]
        if not selected:
            return []

        if self._resolve_adapter is None or not self._resolve_adapter.is_available():
            raise FrameExtractionError("Resolve runtime is unavailable for marker-image extraction.")

        resolve = self._resolve_adapter.raw_handle()
        if resolve is None:
            raise FrameExtractionError("Resolve scripting handle is unavailable for marker-image extraction.")

        project_manager = getattr(resolve, "GetProjectManager", None)
        project = project_manager().GetCurrentProject() if callable(project_manager) else None
        if project is None:
            raise FrameExtractionError("No current Resolve project is available for marker-image extraction.")

        timeline = project.GetCurrentTimeline()
        if timeline is None:
            raise FrameExtractionError("No active Resolve timeline is available for marker-image extraction.")

        start_timecode = str(_safe_call(timeline, "GetStartTimecode") or "01:00:00:00")
        start_frame = int(_safe_call(timeline, "GetStartFrame") or 0)
        frame_rate = _read_frame_rate(timeline, project)

        output_dir = Path(output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)

        previous_timecode = _safe_call(timeline, "GetCurrentTimecode")
        previous_page = _safe_call(resolve, "GetCurrentPage")
        _safe_call(resolve, "OpenPage", "color")

        frames: list[ExtractedMarkerFrame] = []
        try:
            for index, directive in enumerate(selected, start=1):
                output_path = output_dir / f"marker-frame_{index:02d}.jpg"
                timecode = _timecode_from_absolute_frame(
                    absolute_frame=directive.marker.absolute_frame,
                    timeline_start_frame=start_frame,
                    timeline_start_timecode=start_timecode,
                    frame_rate=frame_rate,
                )
                if not _safe_call(timeline, "SetCurrentTimecode", timecode):
                    raise FrameExtractionError(
                        f"Resolve could not seek to marker '{directive.marker.name or directive.marker.timestamp}'."
                    )
                export_method = _export_current_frame(resolve, project, output_path)
                if not export_method:
                    raise FrameExtractionError(
                        f"Resolve could not export an image for marker '{directive.marker.name or directive.marker.timestamp}'."
                    )
                frames.append(
                    ExtractedMarkerFrame(
                        marker_timestamp=directive.marker.timestamp,
                        marker_name=directive.marker.name,
                        image_path=str(output_path),
                        export_method=export_method,
                    )
                )
        finally:
            if previous_timecode:
                _safe_call(timeline, "SetCurrentTimecode", previous_timecode)
            if previous_page and str(previous_page) != "color":
                _safe_call(resolve, "OpenPage", str(previous_page))

        return frames


def _safe_call(target, method_name: str, *args):
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:
        return None


def _read_frame_rate(timeline, project) -> float:
    for owner in (timeline, project):
        raw = _safe_call(owner, "GetSetting", "timelineFrameRate")
        try:
            if raw is not None:
                parsed = float(str(raw).strip())
                if parsed > 0:
                    return parsed
        except ValueError:
            continue
    return 24.0


def _timecode_from_absolute_frame(
    absolute_frame: int,
    timeline_start_frame: int,
    timeline_start_timecode: str,
    frame_rate: float,
) -> str:
    start_tc_frames = _timecode_to_frames(timeline_start_timecode, frame_rate)
    relative_frame = max(0, int(absolute_frame) - int(timeline_start_frame))
    return _frames_to_timecode(start_tc_frames + relative_frame, frame_rate)


def _timecode_to_frames(timecode: str, frame_rate: float) -> int:
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2})[:;](\d{2})$", str(timecode).strip())
    if not match:
        return 0
    hh, mm, ss, ff = (int(part) for part in match.groups())
    fps_base = max(1, int(round(frame_rate)))
    total_seconds = hh * 3600 + mm * 60 + ss
    return total_seconds * fps_base + ff


def _frames_to_timecode(frame_count: int, frame_rate: float) -> str:
    fps_base = max(1, int(round(frame_rate)))
    total_frames = max(0, int(frame_count))
    ff = total_frames % fps_base
    total_seconds = total_frames // fps_base
    ss = total_seconds % 60
    total_minutes = total_seconds // 60
    mm = total_minutes % 60
    hh = (total_minutes // 60) % 24
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def _export_current_frame(resolve, project, output_path: Path) -> str | None:
    attempts = [
        ("project.ExportCurrentFrameAsStill(path)", project, "ExportCurrentFrameAsStill", (str(output_path),)),
        (
            "project.ExportCurrentFrameAsStill(dir,name,ext)",
            project,
            "ExportCurrentFrameAsStill",
            (str(output_path.parent), output_path.stem, "jpg"),
        ),
        ("resolve.ExportCurrentFrameAsStill(path)", resolve, "ExportCurrentFrameAsStill", (str(output_path),)),
        (
            "resolve.ExportCurrentFrameAsStill(dir,name,ext)",
            resolve,
            "ExportCurrentFrameAsStill",
            (str(output_path.parent), output_path.stem, "jpg"),
        ),
    ]
    for method_label, target, method_name, args in attempts:
        exported = _safe_call(target, method_name, *args)
        if not exported:
            continue
        if output_path.exists():
            return method_label
        candidates = sorted(output_path.parent.glob(f"{output_path.stem}*"), key=lambda path: path.stat().st_mtime)
        if candidates:
            try:
                candidates[-1].replace(output_path)
            except OSError:
                return None
            if output_path.exists():
                return method_label
    return None
