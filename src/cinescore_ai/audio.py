from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit

from cinescore_ai.config import AudioProviderSettings
from cinescore_ai.gemini import GeminiExtendPromptPlan, GeminiVideoAnalysisResult
from cinescore_ai.http_client import build_http_session
from cinescore_ai.providers import AudioGenerationStatus, HTTPSession, get_audio_provider
from cinescore_ai.resolve import ImportedAudioPlacement, ResolveAdapter, ResolveTimelineContext


DEFAULT_AUDIO_GENERATION_TIMEOUT_SECONDS = 900.0
DEFAULT_AUDIO_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_MAX_SEGMENT_DURATION_SECONDS = 47


class AudioWorkflowError(RuntimeError):
    pass


@dataclass(slots=True)
class AudioSegmentPlan:
    label: str
    prompt: str
    timestamp: str
    start_seconds: float
    duration_seconds: int
    record_frame: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "prompt": self.prompt,
            "timestamp": self.timestamp,
            "start_seconds": round(self.start_seconds, 3),
            "duration_seconds": self.duration_seconds,
            "record_frame": self.record_frame,
        }


@dataclass(slots=True)
class GeneratedAudioSegment:
    plan: AudioSegmentPlan
    generation_id: str
    status: str
    audio_url: str
    file_path: str
    placement: ImportedAudioPlacement

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "generation_id": self.generation_id,
            "status": self.status,
            "audio_url": self.audio_url,
            "file_path": self.file_path,
            "placement": {
                "file_path": self.placement.file_path,
                "track_index": self.placement.track_index,
                "record_frame": self.placement.record_frame,
                "media_pool_item_name": self.placement.media_pool_item_name,
                "timeline_item_name": self.placement.timeline_item_name,
            },
        }


@dataclass(slots=True)
class AudioCompositionResult:
    output_directory: str
    track_index: int
    segments: list[GeneratedAudioSegment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_display_dict(self) -> dict[str, Any]:
        return {
            "output_directory": self.output_directory,
            "track_index": self.track_index,
            "warnings": list(self.warnings),
            "segments": [segment.to_dict() for segment in self.segments],
        }


@dataclass(slots=True)
class AudioGenerationProgressUpdate:
    phase: str
    message: str
    segment_index: int | None = None
    segment_count: int | None = None
    segment_label: str | None = None
    generation_id: str | None = None
    status: str | None = None
    output_path: str | None = None
    record_frame: int | None = None
    track_index: int | None = None


class AudioWorkflowService:
    def __init__(self, resolve_adapter: ResolveAdapter, session: HTTPSession | None = None) -> None:
        self._resolve_adapter = resolve_adapter
        self._session = session or self._build_session()

    def compose_from_analysis(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        timeline_context: ResolveTimelineContext,
        analysis_result: GeminiVideoAnalysisResult,
        output_directory: str | Path,
        progress_callback=None,
        poll_interval_seconds: float = DEFAULT_AUDIO_POLL_INTERVAL_SECONDS,
        timeout_seconds: float = DEFAULT_AUDIO_GENERATION_TIMEOUT_SECONDS,
    ) -> AudioCompositionResult:
        if self._session is None:
            raise AudioWorkflowError("The 'requests' package is not installed.")
        if not api_key.strip():
            raise AudioWorkflowError("Audio provider API key is required.")

        provider = get_audio_provider(settings.provider_name)
        output_dir = Path(output_directory)
        if timeline_context.project_name:
            output_dir = output_dir / _slugify_fragment(timeline_context.project_name)
        if timeline_context.timeline_name:
            output_dir = output_dir / _slugify_fragment(timeline_context.timeline_name)
        output_dir.mkdir(parents=True, exist_ok=True)

        warnings: list[str] = []
        segment_plans = self._build_segment_plans(analysis_result, timeline_context, warnings)
        if not segment_plans:
            raise AudioWorkflowError("No usable audio segments were produced from the Gemini plan.")

        track_index = self._resolve_adapter.ensure_audio_track()
        self._emit_progress(
            progress_callback,
            AudioGenerationProgressUpdate(
                phase="track",
                message=f"Using Resolve audio track {track_index} for generated music.",
                segment_count=len(segment_plans),
                track_index=track_index,
            ),
        )

        segments: list[GeneratedAudioSegment] = []
        for index, plan in enumerate(segment_plans, start=1):
            self._emit_progress(
                progress_callback,
                AudioGenerationProgressUpdate(
                    phase="requesting",
                    message=f"Requesting audio generation for segment {index}/{len(segment_plans)}: {plan.label}.",
                    segment_index=index,
                    segment_count=len(segment_plans),
                    segment_label=plan.label,
                    record_frame=plan.record_frame,
                    track_index=track_index,
                ),
            )
            initial_status = provider.start_generation(
                api_key=api_key,
                settings=settings,
                prompt=plan.prompt,
                duration_seconds=plan.duration_seconds,
                session=self._session,
            )
            final_status = self._wait_for_generation(
                provider=provider,
                api_key=api_key,
                settings=settings,
                initial_status=initial_status,
                progress_callback=progress_callback,
                plan=plan,
                segment_index=index,
                segment_count=len(segment_plans),
                poll_interval_seconds=poll_interval_seconds,
                timeout_seconds=timeout_seconds,
            )
            if _is_failed_audio_status(final_status.status):
                detail = f" {final_status.error_message}" if final_status.error_message else ""
                raise AudioWorkflowError(
                    f"Audio generation failed for segment '{plan.label}' with status '{final_status.status}'.{detail}"
                )
            if not final_status.audio_url:
                raise AudioWorkflowError(f"Audio generation for segment '{plan.label}' completed without an audio URL.")

            output_path = output_dir / self._build_output_filename(index, plan, final_status.audio_url)
            self._download_audio(final_status.audio_url, output_path, settings)
            placement = self._resolve_adapter.place_audio_clip(
                file_path=str(output_path),
                record_frame=plan.record_frame,
                track_index=track_index,
                timeline_context=timeline_context,
            )
            generated_segment = GeneratedAudioSegment(
                plan=plan,
                generation_id=final_status.generation_id,
                status=final_status.status,
                audio_url=final_status.audio_url,
                file_path=str(output_path),
                placement=placement,
            )
            segments.append(generated_segment)
            self._emit_progress(
                progress_callback,
                AudioGenerationProgressUpdate(
                    phase="placed",
                    message=(
                        f"Placed generated audio for segment '{plan.label}' on track {track_index} "
                        f"at frame {plan.record_frame}."
                    ),
                    segment_index=index,
                    segment_count=len(segment_plans),
                    segment_label=plan.label,
                    generation_id=final_status.generation_id,
                    status=final_status.status,
                    output_path=str(output_path),
                    record_frame=plan.record_frame,
                    track_index=track_index,
                ),
            )

        return AudioCompositionResult(
            output_directory=str(output_dir),
            track_index=track_index,
            segments=segments,
            warnings=warnings,
        )

    def _wait_for_generation(
        self,
        provider,
        api_key: str,
        settings: AudioProviderSettings,
        initial_status: AudioGenerationStatus,
        progress_callback,
        plan: AudioSegmentPlan,
        segment_index: int,
        segment_count: int,
        poll_interval_seconds: float,
        timeout_seconds: float,
    ) -> AudioGenerationStatus:
        current_status = initial_status
        deadline = monotonic() + timeout_seconds

        while True:
            self._emit_progress(
                progress_callback,
                AudioGenerationProgressUpdate(
                    phase="polling",
                    message=(
                        f"Audio generation for segment '{plan.label}' is {current_status.status} "
                        f"(job {current_status.generation_id})."
                    ),
                    segment_index=segment_index,
                    segment_count=segment_count,
                    segment_label=plan.label,
                    generation_id=current_status.generation_id,
                    status=current_status.status,
                    record_frame=plan.record_frame,
                ),
            )
            if _is_complete_audio_status(current_status.status):
                return current_status
            if _is_failed_audio_status(current_status.status):
                return current_status
            if monotonic() >= deadline:
                raise AudioWorkflowError(
                    f"Timed out while waiting for audio generation '{current_status.generation_id}' ({plan.label})."
                )
            sleep(max(0.0, poll_interval_seconds))
            current_status = provider.get_generation_status(
                api_key=api_key,
                settings=settings,
                generation_id=current_status.generation_id,
                session=self._session,
            )

    def _build_segment_plans(
        self,
        analysis_result: GeminiVideoAnalysisResult,
        timeline_context: ResolveTimelineContext,
        warnings: list[str],
    ) -> list[AudioSegmentPlan]:
        plan = analysis_result.plan
        timeline_duration = max(timeline_context.duration_seconds, 1.0)
        extend_points = sorted(
            (
                (_parse_timestamp_seconds(item.timestamp), item)
                for item in plan.extend_prompts
                if item.prompt.strip()
            ),
            key=lambda entry: entry[0],
        )

        segment_plans: list[AudioSegmentPlan] = []

        first_start = extend_points[0][0] if extend_points else timeline_duration
        if plan.base_music_prompt.strip() and (first_start > 0 or not extend_points):
            segment_plans.append(
                self._segment_from_prompt(
                    label="Base cue",
                    prompt=plan.base_music_prompt,
                    timestamp="00:00:00.000",
                    start_seconds=0.0,
                    end_seconds=first_start,
                    timeline_context=timeline_context,
                    warnings=warnings,
                )
            )

        for index, (start_seconds, extend_plan) in enumerate(extend_points):
            end_seconds = extend_points[index + 1][0] if index + 1 < len(extend_points) else timeline_duration
            segment_plans.append(
                self._segment_from_extend_prompt(
                    extend_plan=extend_plan,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    timeline_context=timeline_context,
                    warnings=warnings,
                )
            )

        return [segment for segment in segment_plans if segment.prompt.strip()]

    def _segment_from_extend_prompt(
        self,
        extend_plan: GeminiExtendPromptPlan,
        start_seconds: float,
        end_seconds: float,
        timeline_context: ResolveTimelineContext,
        warnings: list[str],
    ) -> AudioSegmentPlan:
        label_parts = [extend_plan.marker_name.strip() or "Marker cue"]
        if extend_plan.transition_goal.strip():
            label_parts.append(extend_plan.transition_goal.strip())
        label = " - ".join(label_parts[:2])
        return self._segment_from_prompt(
            label=label,
            prompt=extend_plan.prompt,
            timestamp=extend_plan.timestamp,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            timeline_context=timeline_context,
            warnings=warnings,
        )

    def _segment_from_prompt(
        self,
        label: str,
        prompt: str,
        timestamp: str,
        start_seconds: float,
        end_seconds: float,
        timeline_context: ResolveTimelineContext,
        warnings: list[str],
    ) -> AudioSegmentPlan:
        if end_seconds <= start_seconds:
            end_seconds = start_seconds + 1.0

        raw_duration = max(1.0, end_seconds - start_seconds)
        duration_seconds = max(1, int(ceil(raw_duration)))
        if duration_seconds > DEFAULT_MAX_SEGMENT_DURATION_SECONDS:
            warnings.append(
                f"Segment '{label}' was capped at {DEFAULT_MAX_SEGMENT_DURATION_SECONDS}s for provider compatibility."
            )
            duration_seconds = DEFAULT_MAX_SEGMENT_DURATION_SECONDS

        record_frame = timeline_context.start_frame + int(round(start_seconds * timeline_context.frame_rate))
        return AudioSegmentPlan(
            label=label.strip() or "Generated cue",
            prompt=prompt.strip(),
            timestamp=timestamp,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            record_frame=record_frame,
        )

    def _build_output_filename(self, index: int, plan: AudioSegmentPlan, audio_url: str) -> str:
        split = urlsplit(audio_url)
        suffix = Path(split.path).suffix.lower() or ".mp3"
        return f"cinescore-audio_{index:02d}_{_slugify_fragment(plan.label)}{suffix}"

    def _download_audio(self, audio_url: str, output_path: Path, settings: AudioProviderSettings) -> None:
        response = self._session.request(
            "GET",
            audio_url,
            timeout=max(settings.timeout_seconds, 120),
        )
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code >= 400:
            raise AudioWorkflowError(f"Audio download failed from {audio_url} with HTTP {status_code}.")
        content = getattr(response, "content", None)
        if not isinstance(content, (bytes, bytearray)):
            text = getattr(response, "text", "")
            content = text.encode("utf-8")
        output_path.write_bytes(bytes(content))
        
        # Verify file was written successfully
        if not output_path.exists():
            raise AudioWorkflowError(f"Audio file was not created after download: {output_path}")
        file_size = output_path.stat().st_size
        if file_size == 0:
            raise AudioWorkflowError(f"Audio file was created but is empty (0 bytes): {output_path}")

    def _emit_progress(self, progress_callback, update: AudioGenerationProgressUpdate) -> None:
        if callable(progress_callback):
            progress_callback(update)

    def _build_session(self) -> HTTPSession | None:
        return build_http_session()


def _parse_timestamp_seconds(timestamp: str) -> float:
    normalized = timestamp.strip()
    if not normalized:
        return 0.0

    parts = normalized.split(":")
    if len(parts) != 3:
        return 0.0
    try:
        hours = int(parts[0] or 0)
        minutes = int(parts[1] or 0)
        seconds = float(parts[2] or 0)
    except ValueError:
        return 0.0
    return (hours * 3600) + (minutes * 60) + seconds


def _slugify_fragment(value: str) -> str:
    safe_chars = []
    for char in value.lower().strip():
        if char.isalnum():
            safe_chars.append(char)
        elif safe_chars and safe_chars[-1] != "-":
            safe_chars.append("-")
    slug = "".join(safe_chars).strip("-")
    return slug or "cue"


def _is_complete_audio_status(status: str) -> bool:
    normalized = status.strip().lower()
    return normalized in {"completed", "complete", "succeeded", "success"}


def _is_failed_audio_status(status: str) -> bool:
    normalized = status.strip().lower()
    return normalized in {"failed", "error", "cancelled", "canceled"}
