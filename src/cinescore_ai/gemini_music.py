from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from typing import Any
import wave

from cinescore_ai.config import GeminiMusicSettings, GeminiSettings
from cinescore_ai.frame_extractor import ExtractedMarkerFrame, FrameExtractionError, PreviewFrameExtractor
from cinescore_ai.gemini import GeminiVideoAnalysisResult
from cinescore_ai.http_client import build_http_session
from cinescore_ai.marker_directives import MarkerMusicDirective, parse_marker_music_directive
from cinescore_ai.providers import HTTPSession
from cinescore_ai.resolve import ImportedAudioPlacement, ResolveAdapter, ResolveTimelineContext


class GeminiMusicGenerationError(RuntimeError):
    pass


@dataclass(slots=True)
class GeminiMusicCuePlan:
    cue_index: int
    cue_count: int
    label: str
    music_track_slot: int | None
    track_lane: str | None
    track_display_label: str | None
    start_seconds: float
    next_start_seconds: float
    base_duration_seconds: float
    requested_duration_seconds: float
    fade_in_seconds: float
    fade_out_seconds: float
    preferred_fade_seconds: float | None
    vocals_mode: str
    record_frame: int
    track_index: int
    directives: list[MarkerMusicDirective] = field(default_factory=list)
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cue_index": self.cue_index,
            "cue_count": self.cue_count,
            "label": self.label,
            "music_track_slot": self.music_track_slot,
            "track_lane": self.track_lane,
            "track_display_label": self.track_display_label,
            "start_seconds": round(self.start_seconds, 3),
            "next_start_seconds": round(self.next_start_seconds, 3),
            "base_duration_seconds": round(self.base_duration_seconds, 3),
            "requested_duration_seconds": round(self.requested_duration_seconds, 3),
            "fade_in_seconds": round(self.fade_in_seconds, 3),
            "fade_out_seconds": round(self.fade_out_seconds, 3),
            "preferred_fade_seconds": (
                round(self.preferred_fade_seconds, 3) if self.preferred_fade_seconds is not None else None
            ),
            "vocals_mode": self.vocals_mode,
            "record_frame": self.record_frame,
            "track_index": self.track_index,
        }


@dataclass(slots=True)
class GeminiMusicCueResult:
    plan: GeminiMusicCuePlan
    output_path: str
    mime_type: str
    lyrics_or_structure_text: list[str]
    placement: ImportedAudioPlacement
    used_marker_images: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "output_path": self.output_path,
            "mime_type": self.mime_type,
            "lyrics_or_structure_text": list(self.lyrics_or_structure_text),
            "placement": {
                "file_path": self.placement.file_path,
                "track_index": self.placement.track_index,
                "record_frame": self.placement.record_frame,
                "media_pool_folder_name": self.placement.media_pool_folder_name,
                "media_pool_item_name": self.placement.media_pool_item_name,
                "timeline_item_name": self.placement.timeline_item_name,
            },
            "used_marker_images": list(self.used_marker_images),
        }


@dataclass(slots=True)
class GeminiMusicProgressUpdate:
    phase: str
    message: str
    cue_index: int | None = None
    cue_count: int | None = None
    output_path: str | None = None
    image_count: int | None = None
    track_index: int | None = None


@dataclass(slots=True)
class GeminiMusicGenerationResult:
    output_directory: str
    model: str
    vocals_mode: str
    output_format: str
    cues: list[GeminiMusicCueResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_display_dict(self) -> dict[str, Any]:
        return {
            "output_directory": self.output_directory,
            "model": self.model,
            "vocals_mode": self.vocals_mode,
            "output_format": self.output_format,
            "warnings": list(self.warnings),
            "cues": [cue.to_dict() for cue in self.cues],
        }


@dataclass(slots=True)
class _GeneratedCueAudio:
    plan: GeminiMusicCuePlan
    output_path: Path
    mime_type: str
    lyrics_or_structure_text: list[str]
    used_marker_images: list[dict[str, str]]


class GeminiMusicGenerationService:
    def __init__(
        self,
        resolve_adapter: ResolveAdapter,
        frame_extractor: PreviewFrameExtractor | None = None,
        audio_processor=None,
        session: HTTPSession | None = None,
    ) -> None:
        self._resolve_adapter = resolve_adapter
        self._frame_extractor = frame_extractor or PreviewFrameExtractor(resolve_adapter=resolve_adapter)
        self._session = session or self._build_session()

    def generate_from_timeline(
        self,
        api_key: str,
        gemini_settings: GeminiSettings,
        music_settings: GeminiMusicSettings,
        timeline_context: ResolveTimelineContext,
        preview_path: str | Path,
        output_directory: str | Path,
        analysis_result: GeminiVideoAnalysisResult | None = None,
        progress_callback=None,
    ) -> GeminiMusicGenerationResult:
        if self._session is None:
            raise GeminiMusicGenerationError("No HTTP client is available.")
        if not api_key.strip():
            raise GeminiMusicGenerationError("Gemini API key is required.")
        normalized_model = _normalize_music_model_name(music_settings.model)
        if not normalized_model:
            raise GeminiMusicGenerationError("A Gemini music model is required.")

        effective_music_settings = replace(music_settings, model=normalized_model)

        preview_file = Path(preview_path)
        if not preview_file.exists():
            raise GeminiMusicGenerationError(f"Preview file was not found: {preview_file}")

        output_dir = Path(output_directory)
        if timeline_context.project_name:
            output_dir = output_dir / _slugify_fragment(timeline_context.project_name)
        if timeline_context.timeline_name:
            output_dir = output_dir / _slugify_fragment(timeline_context.timeline_name)
        output_dir.mkdir(parents=True, exist_ok=True)

        directives = [parse_marker_music_directive(marker) for marker in timeline_context.markers]
        warnings: list[str] = []
        all_frames = self._extract_all_frames(
            preview_file=preview_file,
            directives=directives,
            output_dir=output_dir / "marker-images",
            music_settings=effective_music_settings,
            warnings=warnings,
            progress_callback=progress_callback,
        )
        cue_plans = self._build_cue_plans(
            timeline_context=timeline_context,
            directives=directives,
            music_settings=effective_music_settings,
            analysis_result=analysis_result,
            warnings=warnings,
        )
        if not cue_plans:
            raise GeminiMusicGenerationError("No Gemini music cues could be planned from the current timeline.")

        self._assign_tracks(cue_plans, timeline_context)
        self._assign_crossfades(cue_plans, music_settings)
        
        # Log track grouping for debugging
        self._log_track_grouping(cue_plans, progress_callback)
        
        generated_cues: list[_GeneratedCueAudio] = []

        # Phase 1: generate and persist all audio files first.
        for cue_plan in cue_plans:
            cue_frames = self._frames_for_cue(cue_plan, all_frames)
            self._emit_progress(
                progress_callback,
                GeminiMusicProgressUpdate(
                    phase="request",
                    message=(
                        f"Generating cue {cue_plan.cue_index}/{cue_plan.cue_count}: {cue_plan.label} "
                        f"on track {cue_plan.track_index}."
                    ),
                    cue_index=cue_plan.cue_index,
                    cue_count=cue_plan.cue_count,
                    image_count=len(cue_frames),
                    track_index=cue_plan.track_index,
                ),
            )
            try:
                response_payload = self._generate_music(
                    api_key=api_key,
                    gemini_settings=gemini_settings,
                    music_settings=effective_music_settings,
                    prompt=cue_plan.prompt,
                    extracted_frames=cue_frames,
                )
                text_parts, inline_audio = self._extract_output(response_payload)
            except GeminiMusicGenerationError as e:
                raise GeminiMusicGenerationError(
                    f"Failed to generate cue {cue_plan.cue_index}/{cue_plan.cue_count} '{cue_plan.label}': {e}"
                ) from e
            
            output_path = output_dir / self._build_output_name(
                music_settings,
                cue_plan,
                returned_mime_type=inline_audio["mime_type"],
            )
            requested_format = music_settings.output_format.lower()
            returned_format = _audio_format_for_mime_type(inline_audio["mime_type"])
            if requested_format == "wav" and returned_format != "wav":
                raise GeminiMusicGenerationError(
                    f"Cue '{cue_plan.label}' requested WAV but Gemini returned {inline_audio['mime_type']}. "
                    "Strict WAV mode rejected the response."
                )
            if requested_format != returned_format:
                warnings.append(
                    f"Cue '{cue_plan.label}' requested {requested_format.upper()} but Gemini returned "
                    f"{inline_audio['mime_type']}."
                )
            output_path.write_bytes(inline_audio["data"])

            if output_path.suffix.lower() == ".wav":
                wav_properties = _read_wav_properties(output_path)
                if wav_properties is None:
                    warnings.append(
                        f"Cue '{cue_plan.label}' was saved as WAV but audio metadata could not be verified."
                    )
                else:
                    sample_rate_hz, bit_depth = wav_properties
                    if sample_rate_hz != 48000:
                        warnings.append(
                            f"Cue '{cue_plan.label}' WAV sample rate is {sample_rate_hz} Hz (expected 48000 Hz)."
                        )
                    if bit_depth < 24:
                        warnings.append(
                            f"Cue '{cue_plan.label}' WAV bit depth is {bit_depth}-bit; target is 24-bit or 32-bit."
                        )

            if not output_path.exists():
                raise GeminiMusicGenerationError(
                    f"Audio file was not created after writing: {output_path}"
                )
            file_size = output_path.stat().st_size
            if file_size == 0:
                raise GeminiMusicGenerationError(
                    f"Audio file was created but is empty (0 bytes): {output_path}"
                )

            generated_cues.append(
                _GeneratedCueAudio(
                    plan=cue_plan,
                    output_path=output_path,
                    mime_type=inline_audio["mime_type"],
                    lyrics_or_structure_text=text_parts,
                    used_marker_images=[
                        {
                            "timestamp": frame.marker_timestamp,
                            "marker_name": frame.marker_name,
                            "image_path": frame.image_path,
                            "export_method": frame.export_method,
                        }
                        for frame in cue_frames
                    ],
                )
            )

        self._emit_progress(
            progress_callback,
            GeminiMusicProgressUpdate(
                phase="generated",
                message=(
                    f"Generated {len(generated_cues)} cue audio file(s). "
                    "Starting Resolve import and timeline placement..."
                ),
            ),
        )

        # Phase 2: import and place all previously generated files.
        cues: list[GeminiMusicCueResult] = []
        for generated in generated_cues:
            cue_plan = generated.plan
            try:
                self._resolve_adapter.ensure_audio_track(track_index=cue_plan.track_index)
                placement = self._resolve_adapter.place_audio_clip(
                    file_path=str(generated.output_path),
                    record_frame=cue_plan.record_frame,
                    track_index=cue_plan.track_index,
                    timeline_context=timeline_context,
                )
            except Exception as exc:
                raise GeminiMusicGenerationError(str(exc)) from exc
            cues.append(
                GeminiMusicCueResult(
                    plan=cue_plan,
                    output_path=str(generated.output_path),
                    mime_type=generated.mime_type,
                    lyrics_or_structure_text=generated.lyrics_or_structure_text,
                    placement=placement,
                    used_marker_images=generated.used_marker_images,
                )
            )
            self._emit_progress(
                progress_callback,
                GeminiMusicProgressUpdate(
                    phase="placed",
                    message=(
                        f"Placed cue {cue_plan.cue_index}/{cue_plan.cue_count} "
                        f"('{cue_plan.label}') on track {cue_plan.track_index}."
                        + (
                            f" Imported into MediaPool folder '{placement.media_pool_folder_name}'."
                            if placement.media_pool_folder_name
                            else ""
                        )
                    ),
                    cue_index=cue_plan.cue_index,
                    cue_count=cue_plan.cue_count,
                    output_path=str(generated.output_path),
                    image_count=len(generated.used_marker_images),
                    track_index=cue_plan.track_index,
                ),
            )

        return GeminiMusicGenerationResult(
            output_directory=str(output_dir),
            model=effective_music_settings.model,
            vocals_mode=effective_music_settings.vocals_mode,
            output_format=effective_music_settings.output_format,
            cues=cues,
            warnings=warnings,
        )

    def _extract_all_frames(
        self,
        preview_file: Path,
        directives: list[MarkerMusicDirective],
        output_dir: Path,
        music_settings: GeminiMusicSettings,
        warnings: list[str],
        progress_callback,
    ) -> list[ExtractedMarkerFrame]:
        if not music_settings.use_marker_images:
            return []
        try:
            frames = self._frame_extractor.extract_marker_frames(
                directives=directives,
                output_directory=output_dir,
                max_images=music_settings.max_images,
            )
        except FrameExtractionError as exc:
            warnings.append(str(exc))
            self._emit_progress(
                progress_callback,
                GeminiMusicProgressUpdate(
                    phase="images",
                    message=f"Marker-image extraction skipped: {exc}",
                    image_count=0,
                ),
            )
            return []

        self._emit_progress(
            progress_callback,
            GeminiMusicProgressUpdate(
                phase="images",
                message=self._build_images_prepared_message(frames),
                image_count=len(frames),
            ),
        )
        return frames

    def _build_images_prepared_message(self, frames: list[ExtractedMarkerFrame]) -> str:
        if not frames:
            return "Prepared 0 marker image(s) for Gemini cue generation."
        methods = [frame.export_method for frame in frames if frame.export_method]
        unique_methods = [method for method in dict.fromkeys(methods)]
        if not unique_methods:
            return f"Prepared {len(frames)} marker image(s) for Gemini cue generation."
        return (
            f"Prepared {len(frames)} marker image(s) for Gemini cue generation "
            f"via Resolve still export: {', '.join(unique_methods)}."
        )

    def _build_cue_plans(
        self,
        timeline_context: ResolveTimelineContext,
        directives: list[MarkerMusicDirective],
        music_settings: GeminiMusicSettings,
        analysis_result: GeminiVideoAnalysisResult | None,
        warnings: list[str],
    ) -> list[GeminiMusicCuePlan]:
        timeline_duration = max(timeline_context.duration_seconds, 1.0)
        use_named_tracks = any(directive.track_lane is not None for directive in directives)
        cue_sources = (
            _group_directives_by_named_track(directives)
            if use_named_tracks
            else _group_directives_by_start(directives)
        )
        if not cue_sources:
            cue_sources = [(0.0, None, [])]
        elif not use_named_tracks and cue_sources[0][0] > 0:
            cue_sources.insert(0, (0.0, None, []))

        cue_count = len(cue_sources)
        plans: list[GeminiMusicCuePlan] = []
        clip_model_warning_added = False
        long_gap_warning_count = 0

        for index, (start_seconds, track_lane, cue_directives) in enumerate(cue_sources, start=1):
            next_start_seconds = _next_cue_boundary_seconds(
                cue_sources=cue_sources,
                current_index=index - 1,
                timeline_duration=timeline_duration,
            )
            base_duration_seconds = max(1.0, next_start_seconds - start_seconds)
            if base_duration_seconds > 120 and long_gap_warning_count < 5:
                warnings.append(
                    f"Cue '{_cue_label(index, cue_directives)}' spans about {base_duration_seconds:.0f}s. "
                    "Add more markers if you want shorter music changes."
                )
                long_gap_warning_count += 1

            fade_out_seconds = 0.0
            fade_in_seconds = 0.0
            music_track_slot = _cue_music_track_slot(cue_directives)
            track_display_label = _cue_track_display_label(cue_directives)
            preferred_fade_seconds = _cue_preferred_fade_seconds(cue_directives, music_settings)
            vocals_mode = _cue_vocals_mode(cue_directives, music_settings)
            explicit_length_seconds = _cue_length_override_seconds(cue_directives)
            marker_duration_seconds = _cue_marker_duration_seconds(cue_directives, timeline_context.frame_rate)
            stop_boundary_seconds = _cue_stop_boundary_seconds(
                directives=cue_directives,
                cue_start_seconds=start_seconds,
                timeline_duration=timeline_duration,
            )

            if music_settings.model == "lyria-3-clip-preview":
                requested_duration_seconds = 30.0
                if not clip_model_warning_added:
                    warnings.append(
                        "The selected Lyria 3 Clip model always produces 30-second clips, so marker durations are approximated."
                    )
                    clip_model_warning_added = True
            else:
                requested_duration_seconds = base_duration_seconds + fade_out_seconds

            if explicit_length_seconds is not None:
                requested_duration_seconds = explicit_length_seconds
                if requested_duration_seconds > base_duration_seconds and next_start_seconds < timeline_duration:
                    warnings.append(
                        f"Cue '{_cue_label(index, cue_directives)}' requested length {requested_duration_seconds:.1f}s "
                        f"but the next marker on the same music lane starts after {base_duration_seconds:.1f}s. "
                        "Clamping to the next same-lane marker."
                    )
                    requested_duration_seconds = base_duration_seconds
            elif marker_duration_seconds is not None:
                requested_duration_seconds = marker_duration_seconds
                if requested_duration_seconds > base_duration_seconds and next_start_seconds < timeline_duration:
                    warnings.append(
                        f"Cue '{_cue_label(index, cue_directives)}' uses marker duration {requested_duration_seconds:.1f}s "
                        f"but the next marker on the same music lane starts after {base_duration_seconds:.1f}s. "
                        "Clamping to the next same-lane marker."
                    )
                    requested_duration_seconds = base_duration_seconds

            if stop_boundary_seconds is not None:
                requested_duration_seconds = min(
                    requested_duration_seconds,
                    max(0.05, stop_boundary_seconds - start_seconds),
                )

            record_frame = timeline_context.start_frame + int(round(start_seconds * timeline_context.frame_rate))
            label = _cue_label(index, cue_directives)
            plan = GeminiMusicCuePlan(
                cue_index=index,
                cue_count=cue_count,
                label=label,
                music_track_slot=music_track_slot,
                track_lane=track_lane,
                track_display_label=track_display_label,
                start_seconds=start_seconds,
                next_start_seconds=next_start_seconds,
                base_duration_seconds=base_duration_seconds,
                requested_duration_seconds=requested_duration_seconds,
                fade_in_seconds=fade_in_seconds,
                fade_out_seconds=fade_out_seconds,
                preferred_fade_seconds=preferred_fade_seconds,
                vocals_mode=vocals_mode,
                record_frame=record_frame,
                track_index=0,
                directives=cue_directives,
            )
            plan.prompt = self._build_prompt(
                cue_plan=plan,
                timeline_context=timeline_context,
                music_settings=music_settings,
                analysis_result=analysis_result,
            )
            plans.append(plan)

        return plans

    def _assign_tracks(self, cue_plans: list[GeminiMusicCuePlan], timeline_context: ResolveTimelineContext) -> None:
        base_track = self._resolve_adapter.ensure_audio_track()
        track_end_frames: dict[int, int] = {}
        next_track = base_track - 1
        named_track_map: dict[str, int] = {}

        for cue_plan in cue_plans:
            assigned_track = None
            if cue_plan.track_lane is not None:
                if cue_plan.track_lane not in named_track_map:
                    if cue_plan.music_track_slot is not None:
                        target_track = base_track + cue_plan.music_track_slot - 1
                    else:
                        target_track = max(base_track, max(named_track_map.values(), default=base_track - 1) + 1)
                    named_track_map[cue_plan.track_lane] = self._resolve_adapter.ensure_audio_track(track_index=target_track)
                assigned_track = named_track_map[cue_plan.track_lane]
            else:
                for track_index in sorted(track_end_frames):
                    if cue_plan.record_frame >= track_end_frames[track_index]:
                        assigned_track = track_index
                        break
                if assigned_track is None:
                    next_track = max(next_track + 1, max(named_track_map.values(), default=base_track - 1) + 1)
                    assigned_track = self._resolve_adapter.ensure_audio_track(track_index=next_track)
                    track_end_frames[assigned_track] = -1

            cue_plan.track_index = assigned_track
            track_end_frames[assigned_track] = cue_plan.record_frame + int(
                round(cue_plan.requested_duration_seconds * timeline_context.frame_rate)
            )

    def _assign_crossfades(self, cue_plans: list[GeminiMusicCuePlan], music_settings: GeminiMusicSettings) -> None:
        global_max_fade = max(0.0, music_settings.crossfade_seconds)
        if global_max_fade <= 0 and not any(plan.preferred_fade_seconds for plan in cue_plans):
            return

        for cue_plan in cue_plans:
            cue_end = cue_plan.start_seconds + cue_plan.requested_duration_seconds
            future_starts = [
                other.start_seconds
                for other in cue_plans
                if other.track_index != cue_plan.track_index
                and other.start_seconds > cue_plan.start_seconds
                and other.start_seconds < cue_end
            ]
            if future_starts:
                overlap = cue_end - min(future_starts)
                max_fade = cue_plan.preferred_fade_seconds if cue_plan.preferred_fade_seconds is not None else global_max_fade
                cue_plan.fade_out_seconds = min(max_fade, max(0.0, overlap))

            previous_overlaps = [
                (other.start_seconds + other.requested_duration_seconds) - cue_plan.start_seconds
                for other in cue_plans
                if other.track_index != cue_plan.track_index
                and other.start_seconds < cue_plan.start_seconds
                and (other.start_seconds + other.requested_duration_seconds) > cue_plan.start_seconds
            ]
            if previous_overlaps:
                max_fade = cue_plan.preferred_fade_seconds if cue_plan.preferred_fade_seconds is not None else global_max_fade
                cue_plan.fade_in_seconds = min(max_fade, max(0.0, max(previous_overlaps)))

    def _frames_for_cue(
        self,
        cue_plan: GeminiMusicCuePlan,
        all_frames: list[ExtractedMarkerFrame],
    ) -> list[ExtractedMarkerFrame]:
        timestamps = {directive.marker.timestamp for directive in cue_plan.directives if directive.use_image}
        selected = [frame for frame in all_frames if frame.marker_timestamp in timestamps]
        return selected[:10]

    def _generate_music(
        self,
        api_key: str,
        gemini_settings: GeminiSettings,
        music_settings: GeminiMusicSettings,
        prompt: str,
        extracted_frames: list[ExtractedMarkerFrame],
    ) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for frame in extracted_frames:
            image_bytes = Path(frame.image_path).read_bytes()
            parts.append(
                {
                    "inline_data": {
                        "mime_type": frame.mime_type,
                        "data": b64encode(image_bytes).decode("ascii"),
                    }
                }
            )

        payload: dict[str, Any] = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["AUDIO", "TEXT"],
            },
        }
        if music_settings.output_format.lower() == "wav":
            payload["generationConfig"]["responseMimeType"] = "audio/wav"

        endpoint = f"{gemini_settings.endpoint.rstrip('/')}/{music_settings.model}:generateContent"
        request_headers = {
            "x-goog-api-key": api_key.strip(),
            "Content-Type": "application/json",
        }
        timeout = max(gemini_settings.timeout_seconds, 180)

        response = self._session.request(
            "POST",
            endpoint,
            headers=request_headers,
            json=payload,
            timeout=timeout,
        )
        status_code = int(getattr(response, "status_code", 0) or 0)
        body = getattr(response, "text", "")

        if (
            status_code >= 400
            and music_settings.output_format.lower() == "wav"
            and "responseMimeType" in payload.get("generationConfig", {})
            and _response_mime_type_rejected(body)
        ):
            retry_payload = {
                "contents": payload["contents"],
                "generationConfig": {
                    "responseModalities": ["AUDIO", "TEXT"],
                },
            }
            response = self._session.request(
                "POST",
                endpoint,
                headers=request_headers,
                json=retry_payload,
                timeout=timeout,
            )
            status_code = int(getattr(response, "status_code", 0) or 0)
            body = getattr(response, "text", "")

        if status_code >= 400:
            raise GeminiMusicGenerationError(f"Gemini music generation failed (HTTP {status_code}): {body[:240]}")
        result = response.json()
        if not isinstance(result, dict):
            raise GeminiMusicGenerationError("Gemini music generation returned invalid JSON.")
        return result

    def _extract_output(self, payload: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            error_message = f"Gemini music generation returned no candidates."
            if "error" in payload:
                error_info = payload.get("error", {})
                error_details = error_info.get("message", "Unknown error")
                error_message += f" Error: {error_details}"
            raise GeminiMusicGenerationError(error_message)
        candidate = candidates[0] if isinstance(candidates[0], dict) else {}
        content = candidate.get("content")
        if not isinstance(content, dict):
            candidate_summary = str(candidate)[:200] if candidate else "empty candidate"
            error_message = f"Gemini music candidate did not include content. Candidate: {candidate_summary}"
            if candidate.get("finishReason"):
                error_message += f" (Finish reason: {candidate.get('finishReason')})"
            raise GeminiMusicGenerationError(error_message)
        parts = content.get("parts")
        if not isinstance(parts, list):
            raise GeminiMusicGenerationError("Gemini music candidate did not include parts.")

        text_parts: list[str] = []
        inline_audio: dict[str, Any] | None = None
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
            inline_data = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline_data, dict) and inline_audio is None:
                encoded = inline_data.get("data")
                mime_type = str(inline_data.get("mimeType") or inline_data.get("mime_type") or "audio/mpeg")
                if isinstance(encoded, str):
                    inline_audio = {"mime_type": mime_type, "data": b64decode(encoded)}

        if inline_audio is None:
            raise GeminiMusicGenerationError("Gemini music generation did not return inline audio data.")
        return text_parts, inline_audio

    def _log_track_grouping(self, cue_plans: list[GeminiMusicCuePlan], progress_callback=None) -> None:
        """Log how cues are grouped on tracks for debugging purposes."""
        from collections import defaultdict
        track_groups: dict[int, list[GeminiMusicCuePlan]] = defaultdict(list)
        for cue_plan in cue_plans:
            track_groups[cue_plan.track_index].append(cue_plan)
        
        grouping_lines: list[str] = []
        grouping_lines.append(f"Music generation plan: {len(cue_plans)} cue(s) on {len(track_groups)} track(s):")
        for track_idx in sorted(track_groups.keys()):
            cues = track_groups[track_idx]
            cue_info = ", ".join(
                f"cue {c.cue_index} '{c.label}' @ {c.start_seconds:.1f}s"
                for c in sorted(cues, key=lambda c: c.start_seconds)
            )
            grouping_lines.append(f"  Track {track_idx}: {cue_info}")
        
        grouping_message = "\n".join(grouping_lines)
        self._emit_progress(
            progress_callback,
            GeminiMusicProgressUpdate(
                phase="plan",
                message=grouping_message,
            ),
        )

    def _build_prompt(
        self,
        cue_plan: GeminiMusicCuePlan,
        timeline_context: ResolveTimelineContext,
        music_settings: GeminiMusicSettings,
        analysis_result: GeminiVideoAnalysisResult | None,
    ) -> str:
        if analysis_result is not None:
            summary = analysis_result.plan.timeline_summary.strip()
            base_prompt = analysis_result.plan.base_music_prompt.strip()
        else:
            summary = ""
            base_prompt = ""

        vocals_instruction = (
            "Instrumental only, no vocals."
            if cue_plan.vocals_mode == "instrumental"
            else "Include vocals and lyrics for this cue."
        )
        
        # Extract only marker notes (not theme names) to avoid copyright filters
        note_lines = []
        cue_keywords = _cue_style_keywords(cue_plan.directives)
        if cue_plan.directives:
            for directive in cue_plan.directives:
                # Use only the marker note/instruction, not the theme label
                note = directive.cleaned_note or directive.marker.note or ""
                if note:
                    note_lines.append(f"- {directive.marker.timestamp} {note}")
                if directive.style_keywords:
                    note_lines.append(f"  Keywords: {', '.join(directive.style_keywords)}")
        else:
            note_lines.append("- Intro section before the first marker.")

        transition_instruction = ""
        if cue_plan.fade_out_seconds > 0:
            transition_instruction = (
                f" End this cue with about {cue_plan.fade_out_seconds:.1f} seconds of crossfade-friendly tail "
                "because the next cue starts before this one fully leaves."
            )
        stop_directive = _cue_stop_directive(cue_plan.directives, cue_plan.start_seconds)
        stop_instruction = ""
        if stop_directive is not None:
            stop_timestamp = stop_directive.marker.timestamp
            stop_relative = max(0.0, stop_directive.marker.relative_seconds - cue_plan.start_seconds)
            stop_mode = _cue_stop_mode(stop_directive)
            if stop_mode == "hard":
                stop_instruction = (
                    f" This cue must stop exactly at {stop_timestamp} with an abrupt hard cut. "
                    "Do not add tail reverb, release, or fade beyond that timestamp."
                )
            elif stop_relative > 0:
                suggested_outro = min(3.0, max(0.8, stop_relative * 0.35))
                stop_instruction = (
                    f" This cue must resolve naturally and end exactly at {stop_timestamp}. "
                    f"Start a musical outro about {min(suggested_outro, stop_relative):.1f}s before the end and "
                    "avoid abrupt truncation."
                )

        # Use generic cue label to avoid copyright issues with specific theme names
        generic_cue_label = f"Cue {cue_plan.cue_index}"
        
        prompt_parts = [
            f"Compose cue {cue_plan.cue_index} of {cue_plan.cue_count} for an edited video timeline.",
            f"Cue identifier: {generic_cue_label}",
        ]
        if cue_plan.music_track_slot is not None:
            prompt_parts.append(f"Music track slot: {cue_plan.music_track_slot}")
        elif cue_plan.track_display_label:
            prompt_parts.append(f"Music track lane: {cue_plan.track_display_label}")
        prompt_parts.extend(
            [
                f"Start time: {cue_plan.start_seconds:.1f}s",
                f"Target section length before the next cue: about {cue_plan.base_duration_seconds:.1f}s",
                f"Requested cue length: about {cue_plan.requested_duration_seconds:.1f}s",
                f"Vocals mode: {vocals_instruction}",
                f"Project: {timeline_context.project_name}",
                f"Timeline: {timeline_context.timeline_name}",
            ]
        )
        if summary:
            prompt_parts.append(f"Overall music summary: {summary}")
        if base_prompt:
            prompt_parts.append(f"Overall style anchor: {base_prompt}")
        if cue_keywords:
            prompt_parts.append(f"Style keywords for this cue: {', '.join(cue_keywords)}")
        genre_tags = _cue_genre_tags(cue_plan.directives)
        if genre_tags:
            prompt_parts.append(f"Genre = {', '.join(genre_tags)}")
        instruments = _cue_instruments(cue_plan.directives)
        if instruments:
            prompt_parts.append(f"Instruments = {', '.join(instruments)}")
        bpm = _cue_bpm(cue_plan.directives)
        if bpm is not None:
            prompt_parts.append(f"BPM = {bpm}")
        key_scale = _cue_key_scale(cue_plan.directives)
        if key_scale:
            prompt_parts.append(f"Key/Scale = {key_scale}")
        mood_tags = _cue_mood_tags(cue_plan.directives)
        if mood_tags:
            prompt_parts.append(f"Mood = {', '.join(mood_tags)}")
        structure_tags = _cue_structure_tags(cue_plan.directives)
        if structure_tags:
            prompt_parts.append(f"Structure = {', '.join(structure_tags)}")
        if music_settings.output_format.lower() == "wav":
            prompt_parts.append("Audio target = 48 kHz stereo WAV, prefer 32-bit float, minimum 24-bit.")
        structured_inputs = _cue_input_lines(cue_plan.directives)
        if structured_inputs:
            prompt_parts.append("Structured inputs:")
            prompt_parts.extend(structured_inputs)
        prompt_parts.append("Structured prompt JSON:")
        prompt_parts.append(_cue_structured_json(cue_plan))
        prompt_parts.append("Musical directives for this cue:")
        prompt_parts.extend(note_lines)
        prompt = "\n".join(prompt_parts)
        if transition_instruction:
            prompt += transition_instruction
        if stop_instruction:
            prompt += stop_instruction
        prompt += "\nIf images are attached, use them as visual references for this cue only. "
        prompt += "Return audio and any useful lyrics or structure text."
        return prompt

    def _build_output_name(
        self,
        music_settings: GeminiMusicSettings,
        cue_plan: GeminiMusicCuePlan,
        returned_mime_type: str,
    ) -> str:
        requested_extension = ".wav" if music_settings.output_format.lower() == "wav" else ".mp3"
        extension = _file_extension_for_audio_mime_type(returned_mime_type, requested_extension)
        slug = _slugify_fragment(cue_plan.label)
        slot_fragment = ""
        if cue_plan.music_track_slot is not None:
            slot_fragment = f"track_{cue_plan.music_track_slot:02d}_"
        elif cue_plan.track_display_label:
            slot_fragment = f"track_{_slugify_fragment(cue_plan.track_display_label)}_"
        return f"{slot_fragment}{slug}{extension}"

    def _emit_progress(self, progress_callback, update: GeminiMusicProgressUpdate) -> None:
        if callable(progress_callback):
            progress_callback(update)

    def _build_session(self) -> HTTPSession | None:
        return build_http_session()


def _cue_genre_tags(directives: list[MarkerMusicDirective]) -> list[str]:
    tags: list[str] = []
    for directive in directives:
        for tag in directive.genre_tags:
            if tag not in tags:
                tags.append(tag)
    return tags


def _cue_instruments(directives: list[MarkerMusicDirective]) -> list[str]:
    items: list[str] = []
    for directive in directives:
        for item in directive.instruments:
            if item not in items:
                items.append(item)
    return items


def _cue_bpm(directives: list[MarkerMusicDirective]) -> int | None:
    for directive in reversed(directives):
        if directive.bpm is not None:
            return directive.bpm
    return None


def _cue_key_scale(directives: list[MarkerMusicDirective]) -> str | None:
    for directive in reversed(directives):
        if directive.key_scale:
            return directive.key_scale
    return None


def _cue_mood_tags(directives: list[MarkerMusicDirective]) -> list[str]:
    items: list[str] = []
    for directive in directives:
        for item in directive.mood_tags:
            if item not in items:
                items.append(item)
    return items


def _cue_structure_tags(directives: list[MarkerMusicDirective]) -> list[str]:
    items: list[str] = []
    for directive in directives:
        for item in directive.structure_tags:
            if item not in items:
                items.append(item)
    return items


def _cue_input_lines(directives: list[MarkerMusicDirective]) -> list[str]:
    lines: list[str] = []
    for directive in directives:
        has_genre = bool(directive.genre_tags)
        has_input = bool(directive.input_text)
        if not has_genre and not has_input:
            continue
        lines.append(f"[{directive.marker.timestamp}]")
        if has_genre:
            lines.append(f"Genre = {', '.join(directive.genre_tags)}")
        if has_input:
            lines.append(f"Input = {directive.input_text}")
    return lines


def _cue_structured_json(cue_plan: GeminiMusicCuePlan) -> str:
    stop_directive = _cue_stop_directive(cue_plan.directives, cue_plan.start_seconds)
    stop_mode = _cue_stop_mode(stop_directive)
    payload: dict[str, Any] = {
        "cue": {
            "index": cue_plan.cue_index,
            "count": cue_plan.cue_count,
            "start_seconds": round(cue_plan.start_seconds, 3),
            "target_duration_seconds": round(cue_plan.requested_duration_seconds, 3),
            "track_slot": cue_plan.music_track_slot,
            "track_lane": cue_plan.track_display_label or cue_plan.track_lane,
            "stop_timestamp": stop_directive.marker.timestamp if stop_directive is not None else None,
            "stop_mode": stop_mode,
            "genres": _cue_genre_tags(cue_plan.directives),
            "instruments": _cue_instruments(cue_plan.directives),
            "bpm": _cue_bpm(cue_plan.directives),
            "key_scale": _cue_key_scale(cue_plan.directives),
            "mood": _cue_mood_tags(cue_plan.directives),
            "structure": _cue_structure_tags(cue_plan.directives),
            "vocals_mode": cue_plan.vocals_mode,
        },
        "marker_inputs": [
            {
                "timestamp": directive.marker.timestamp,
                "genre": list(directive.genre_tags),
                "input": directive.input_text,
                "stop": directive.stop_here,
                "stop_mode": directive.stop_mode,
            }
            for directive in cue_plan.directives
            if directive.genre_tags or directive.input_text or directive.stop_here
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _cue_stop_boundary_seconds(
    directives: list[MarkerMusicDirective],
    cue_start_seconds: float,
    timeline_duration: float,
) -> float | None:
    stop_candidates = [
        directive.marker.relative_seconds
        for directive in directives
        if directive.stop_here and directive.marker.relative_seconds >= cue_start_seconds
    ]
    if not stop_candidates:
        return None
    return min(max(cue_start_seconds, min(stop_candidates)), timeline_duration)


def _cue_stop_directive(
    directives: list[MarkerMusicDirective],
    cue_start_seconds: float,
) -> MarkerMusicDirective | None:
    stop_directives = [
        directive
        for directive in directives
        if directive.stop_here and directive.marker.relative_seconds >= cue_start_seconds
    ]
    if not stop_directives:
        return None
    return min(stop_directives, key=lambda directive: directive.marker.relative_seconds)


def _cue_stop_mode(directive: MarkerMusicDirective | None) -> str | None:
    if directive is None:
        return None
    if directive.stop_mode in {"hard", "natural"}:
        return directive.stop_mode
    return "natural" if directive.stop_here else None


def _read_wav_properties(file_path: Path) -> tuple[int, int] | None:
    try:
        with wave.open(str(file_path), "rb") as wav_file:
            sample_rate_hz = int(wav_file.getframerate())
            bit_depth = int(wav_file.getsampwidth()) * 8
            return sample_rate_hz, bit_depth
    except (wave.Error, OSError, ValueError):
        return None


def _group_directives_by_start(
    directives: list[MarkerMusicDirective],
) -> list[tuple[float, str | None, list[MarkerMusicDirective]]]:
    grouped: dict[float, list[MarkerMusicDirective]] = {}
    for directive in directives:
        key = round(directive.marker.relative_seconds, 3)
        grouped.setdefault(key, []).append(directive)
    return [(start, None, grouped[start]) for start in sorted(grouped)]


def _group_directives_by_named_track(
    directives: list[MarkerMusicDirective],
) -> list[tuple[float, str | None, list[MarkerMusicDirective]]]:
    grouped: dict[str | None, list[MarkerMusicDirective]] = {}
    for directive in directives:
        lane = directive.track_lane or f"unassigned:{round(directive.marker.relative_seconds, 3)}"
        grouped.setdefault(lane, []).append(directive)

    lane_groups: list[tuple[float, str | None, list[MarkerMusicDirective]]] = []
    for lane, grouped_directives in grouped.items():
        ordered_directives = sorted(grouped_directives, key=lambda item: item.marker.relative_seconds)
        start_seconds = round(ordered_directives[0].marker.relative_seconds, 3)
        track_lane = None if lane.startswith("unassigned:") else lane
        lane_groups.append((start_seconds, track_lane, ordered_directives))

    lane_groups.sort(key=lambda item: (item[0], item[1] or ""))
    return lane_groups


def _next_cue_boundary_seconds(
    cue_sources: list[tuple[float, str | None, list[MarkerMusicDirective]]],
    current_index: int,
    timeline_duration: float,
) -> float:
    start_seconds, track_lane, _ = cue_sources[current_index]
    if track_lane is None:
        if current_index + 1 < len(cue_sources):
            return cue_sources[current_index + 1][0]
        return timeline_duration

    for next_index in range(current_index + 1, len(cue_sources)):
        next_start_seconds, next_lane, _ = cue_sources[next_index]
        if next_lane == track_lane:
            return next_start_seconds
    return timeline_duration


def _cue_label(index: int, directives: list[MarkerMusicDirective]) -> str:
    if not directives:
        return "Intro"
    for directive in directives:
        if directive.theme_label:
            return directive.theme_label
        if directive.section_label:
            return directive.section_label
        if directive.marker.name:
            return directive.marker.name
    return f"Cue {index}"


def _cue_music_track_slot(directives: list[MarkerMusicDirective]) -> int | None:
    for directive in directives:
        if directive.music_track_slot is not None:
            return directive.music_track_slot
    return None


def _cue_track_display_label(directives: list[MarkerMusicDirective]) -> str | None:
    for directive in directives:
        if directive.track_display_label:
            return directive.track_display_label
    return None


def _normalize_music_model_name(model_name: str) -> str:
    normalized = str(model_name).strip()
    if not normalized:
        return ""
    if normalized.lower().startswith("models/"):
        normalized = normalized.split("/", 1)[1]

    lowered = " ".join(normalized.replace("_", " ").replace("-", " ").lower().split())
    if lowered == "lyria 3 pro":
        return "lyria-3-pro-preview"
    if lowered == "lyria 3 clip":
        return "lyria-3-clip-preview"

    return normalized


def _file_extension_for_audio_mime_type(mime_type: str, fallback_extension: str) -> str:
    normalized = (mime_type or "").strip().lower()
    if "wav" in normalized or "wave" in normalized:
        return ".wav"
    if "mpeg" in normalized or "mp3" in normalized:
        return ".mp3"
    return fallback_extension


def _audio_format_for_mime_type(mime_type: str) -> str:
    extension = _file_extension_for_audio_mime_type(mime_type, ".mp3")
    return "wav" if extension == ".wav" else "mp3"


def _response_mime_type_rejected(response_text: str) -> bool:
    normalized = (response_text or "").lower()
    return "response_mime_type" in normalized and "allowed mimetypes" in normalized


def _cue_preferred_fade_seconds(
    directives: list[MarkerMusicDirective],
    music_settings: GeminiMusicSettings,
) -> float | None:
    for directive in reversed(directives):
        if directive.fade_seconds is not None:
            return directive.fade_seconds
    default_fade = max(0.0, music_settings.crossfade_seconds)
    return default_fade if default_fade > 0 else None


def _cue_length_override_seconds(directives: list[MarkerMusicDirective]) -> float | None:
    for directive in reversed(directives):
        if directive.length_seconds is not None:
            return directive.length_seconds
    return None


def _cue_marker_duration_seconds(directives: list[MarkerMusicDirective], frame_rate: float) -> float | None:
    if frame_rate <= 0:
        return None
    if len(directives) != 1:
        return None
    for directive in directives:
        duration_frames = int(directive.marker.duration_frames)
        if duration_frames > 0:
            return max(0.05, duration_frames / frame_rate)
    return None


def _cue_vocals_mode(
    directives: list[MarkerMusicDirective],
    music_settings: GeminiMusicSettings,
) -> str:
    for directive in reversed(directives):
        if directive.vocals_mode is not None:
            return directive.vocals_mode
    return music_settings.vocals_mode


def _cue_style_keywords(directives: list[MarkerMusicDirective]) -> list[str]:
    keywords: list[str] = []
    for directive in directives:
        for keyword in directive.style_keywords:
            if keyword not in keywords:
                keywords.append(keyword)
    return keywords


def _slugify_fragment(value: str) -> str:
    safe = []
    for char in value.lower().strip():
        if char.isalnum():
            safe.append(char)
        elif safe and safe[-1] != "-":
            safe.append("-")
    return "".join(safe).strip("-") or "cue"
