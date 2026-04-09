from __future__ import annotations

from dataclasses import dataclass
import json
import mimetypes
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from cinescore_ai.config import GeminiSettings
from cinescore_ai.http_client import build_http_session
from cinescore_ai.providers import HTTPSession
from cinescore_ai.resolve import ResolveTimelineContext


DEFAULT_FILE_PROCESSING_TIMEOUT_SECONDS = 600.0
DEFAULT_FILE_POLL_INTERVAL_SECONDS = 5.0


class GeminiAnalysisError(RuntimeError):
    pass


@dataclass(slots=True)
class GeminiAnalysisProgressUpdate:
    phase: str
    message: str
    preview_path: str | None = None
    remote_file_name: str | None = None
    remote_state: str | None = None


@dataclass(slots=True)
class GeminiExtendPromptPlan:
    timestamp: str
    marker_name: str
    marker_note: str
    prompt: str
    transition_goal: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GeminiExtendPromptPlan":
        return cls(
            timestamp=str(payload.get("timestamp", "")),
            marker_name=str(payload.get("marker_name", "")),
            marker_note=str(payload.get("marker_note", "")),
            prompt=str(payload.get("prompt", "")),
            transition_goal=str(payload.get("transition_goal", "")),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "marker_name": self.marker_name,
            "marker_note": self.marker_note,
            "prompt": self.prompt,
            "transition_goal": self.transition_goal,
        }


@dataclass(slots=True)
class GeminiMusicPromptPlan:
    timeline_summary: str
    base_music_prompt: str
    extend_prompts: list[GeminiExtendPromptPlan]
    mix_notes: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GeminiMusicPromptPlan":
        extend_prompts_payload = payload.get("extend_prompts", [])
        extend_prompts = []
        if isinstance(extend_prompts_payload, list):
            for item in extend_prompts_payload:
                if isinstance(item, dict):
                    extend_prompts.append(GeminiExtendPromptPlan.from_dict(item))

        mix_notes_payload = payload.get("mix_notes", [])
        mix_notes = [str(item) for item in mix_notes_payload] if isinstance(mix_notes_payload, list) else []

        return cls(
            timeline_summary=str(payload.get("timeline_summary", "")),
            base_music_prompt=str(payload.get("base_music_prompt", "")),
            extend_prompts=extend_prompts,
            mix_notes=mix_notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeline_summary": self.timeline_summary,
            "base_music_prompt": self.base_music_prompt,
            "extend_prompts": [item.to_dict() for item in self.extend_prompts],
            "mix_notes": list(self.mix_notes),
        }


@dataclass(slots=True)
class GeminiVideoAnalysisResult:
    preview_path: str
    remote_file_name: str | None
    remote_file_uri: str | None
    remote_cleanup_attempted: bool
    remote_cleanup_succeeded: bool
    plan: GeminiMusicPromptPlan
    raw_json: dict[str, Any]

    def to_display_dict(self) -> dict[str, Any]:
        return {
            "preview_path": self.preview_path,
            "remote_file_name": self.remote_file_name,
            "remote_file_uri": self.remote_file_uri,
            "remote_cleanup_attempted": self.remote_cleanup_attempted,
            "remote_cleanup_succeeded": self.remote_cleanup_succeeded,
            "analysis": self.plan.to_dict(),
        }


class GeminiVideoAnalysisService:
    def __init__(self, session: HTTPSession | None = None) -> None:
        self._session = session or self._build_session()

    def analyze_preview(
        self,
        api_key: str,
        settings: GeminiSettings,
        timeline_context: ResolveTimelineContext,
        preview_path: str | Path,
        progress_callback=None,
    ) -> GeminiVideoAnalysisResult:
        if self._session is None:
            raise GeminiAnalysisError("The 'requests' package is not installed.")
        if not api_key.strip():
            raise GeminiAnalysisError("Gemini API key is required.")

        preview_file = Path(preview_path)
        if not preview_file.exists():
            raise GeminiAnalysisError(f"Preview file was not found: {preview_file}")

        mime_type = mimetypes.guess_type(preview_file.name)[0] or "application/octet-stream"
        if mime_type != "video/mp4":
            raise GeminiAnalysisError(f"Preview file must be an MP4 video. Detected MIME type: {mime_type}")

        self._emit_progress(
            progress_callback,
            GeminiAnalysisProgressUpdate(
                phase="preparing",
                message=f"Preparing Gemini analysis for {preview_file}.",
                preview_path=str(preview_file),
            ),
        )

        remote_file_name: str | None = None
        remote_file_uri: str | None = None
        remote_cleanup_attempted = False
        remote_cleanup_succeeded = False
        analysis_json: dict[str, Any] | None = None
        plan: GeminiMusicPromptPlan | None = None
        try:
            uploaded = self._upload_file(api_key=api_key, settings=settings, preview_file=preview_file, mime_type=mime_type)
            remote_file_name = uploaded["name"]
            remote_file_uri = uploaded["uri"]
            self._emit_progress(
                progress_callback,
                GeminiAnalysisProgressUpdate(
                    phase="uploaded",
                    message=f"Uploaded preview to Gemini as {remote_file_name}.",
                    preview_path=str(preview_file),
                    remote_file_name=remote_file_name,
                    remote_state=uploaded.get("state"),
                ),
            )

            active_file = self._wait_for_file_active(
                api_key=api_key,
                settings=settings,
                file_name=remote_file_name,
                progress_callback=progress_callback,
                preview_path=str(preview_file),
            )
            remote_file_uri = str(active_file.get("uri", remote_file_uri or ""))

            self._emit_progress(
                progress_callback,
                GeminiAnalysisProgressUpdate(
                    phase="generating",
                    message=f"Requesting structured Gemini analysis from model {settings.model}.",
                    preview_path=str(preview_file),
                    remote_file_name=remote_file_name,
                    remote_state=str(active_file.get("state", "ACTIVE")),
                ),
            )
            analysis_json = self._generate_structured_analysis(
                api_key=api_key,
                settings=settings,
                file_uri=remote_file_uri,
                mime_type=mime_type,
                timeline_context=timeline_context,
            )
            plan = GeminiMusicPromptPlan.from_dict(analysis_json)
            self._validate_plan(plan)
            self._emit_progress(
                progress_callback,
                GeminiAnalysisProgressUpdate(
                    phase="generated",
                    message=f"Gemini returned a structured music plan for {preview_file.name}.",
                    preview_path=str(preview_file),
                    remote_file_name=remote_file_name,
                    remote_state=str(active_file.get("state", "ACTIVE")),
                ),
            )
        finally:
            if remote_file_name:
                remote_cleanup_attempted = True
                remote_cleanup_succeeded = self._delete_file(api_key=api_key, settings=settings, file_name=remote_file_name)
                self._emit_progress(
                    progress_callback,
                    GeminiAnalysisProgressUpdate(
                        phase="cleanup",
                        message=(
                            f"Deleted Gemini upload {remote_file_name}."
                            if remote_cleanup_succeeded
                            else f"Could not delete Gemini upload {remote_file_name}."
                        ),
                        preview_path=str(preview_file),
                        remote_file_name=remote_file_name,
                    ),
                )

        if analysis_json is None or plan is None:
            raise GeminiAnalysisError("Gemini analysis did not produce a valid music plan.")

        return GeminiVideoAnalysisResult(
            preview_path=str(preview_file),
            remote_file_name=remote_file_name,
            remote_file_uri=remote_file_uri,
            remote_cleanup_attempted=remote_cleanup_attempted,
            remote_cleanup_succeeded=remote_cleanup_succeeded,
            plan=plan,
            raw_json=analysis_json,
        )

    def _upload_file(
        self,
        api_key: str,
        settings: GeminiSettings,
        preview_file: Path,
        mime_type: str,
    ) -> dict[str, Any]:
        file_bytes = preview_file.read_bytes()
        response = self._session.request(
            "POST",
            self._upload_files_url(settings),
            headers={
                "x-goog-api-key": api_key.strip(),
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(file_bytes)),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            },
            json={"file": {"display_name": preview_file.name}},
            timeout=max(settings.timeout_seconds, 60),
        )
        self._raise_for_error(response, "Gemini upload start failed")
        upload_url = response.headers.get("X-Goog-Upload-URL") or response.headers.get("x-goog-upload-url")
        if not upload_url:
            raise GeminiAnalysisError("Gemini upload start response did not include an upload URL.")

        upload_response = self._session.request(
            "POST",
            upload_url,
            headers={
                "Content-Length": str(len(file_bytes)),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
            data=file_bytes,
            timeout=max(settings.timeout_seconds, 120),
        )
        self._raise_for_error(upload_response, "Gemini file upload failed")
        upload_payload = self._parse_json(upload_response, "Gemini file upload returned invalid JSON")
        file_payload = self._extract_file_payload(upload_payload, "Gemini file upload response did not include file metadata.")
        if not file_payload.get("name") or not file_payload.get("uri"):
            raise GeminiAnalysisError("Gemini file upload response was missing required file identifiers.")
        return file_payload

    def _wait_for_file_active(
        self,
        api_key: str,
        settings: GeminiSettings,
        file_name: str,
        progress_callback,
        preview_path: str,
    ) -> dict[str, Any]:
        deadline = monotonic() + DEFAULT_FILE_PROCESSING_TIMEOUT_SECONDS
        while True:
            response = self._session.request(
                "GET",
                f"{self._api_root(settings)}/{file_name}",
                headers={"x-goog-api-key": api_key.strip()},
                timeout=max(settings.timeout_seconds, 60),
            )
            self._raise_for_error(response, "Gemini file status lookup failed")
            payload = self._parse_json(response, "Gemini file status response returned invalid JSON")
            file_payload = self._extract_file_payload(payload, "Gemini file status response did not include file metadata.")
            state = str(file_payload.get("state", "STATE_UNSPECIFIED"))
            self._emit_progress(
                progress_callback,
                GeminiAnalysisProgressUpdate(
                    phase="processing",
                    message=f"Gemini file {file_name} is in state {state}.",
                    preview_path=preview_path,
                    remote_file_name=file_name,
                    remote_state=state,
                ),
            )
            if state == "ACTIVE":
                return file_payload
            if state == "FAILED":
                raise GeminiAnalysisError(f"Gemini failed to process uploaded preview file {file_name}.")
            if monotonic() >= deadline:
                raise GeminiAnalysisError(f"Timed out while waiting for Gemini to process file {file_name}.")
            sleep(DEFAULT_FILE_POLL_INTERVAL_SECONDS)

    def _generate_structured_analysis(
        self,
        api_key: str,
        settings: GeminiSettings,
        file_uri: str,
        mime_type: str,
        timeline_context: ResolveTimelineContext,
    ) -> dict[str, Any]:
        prompt = self._build_analysis_prompt(timeline_context)
        response = self._session.request(
            "POST",
            f"{self._api_root(settings)}/models/{settings.model}:generateContent",
            headers={
                "x-goog-api-key": api_key.strip(),
                "Content-Type": "application/json",
            },
            json={
                "systemInstruction": {
                    "parts": [
                        {
                            "text": (
                                "You are an expert music supervisor and prompt engineer for generative soundtrack tools. "
                                "Analyze the uploaded edited video and return only valid JSON matching the provided schema. "
                                "Treat marker timestamps as relative to the uploaded preview file, not the project's absolute start timecode."
                            )
                        }
                    ]
                },
                "contents": [
                    {
                        "parts": [
                            {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                            {"text": prompt},
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": _music_plan_schema(),
                    "temperature": 0.3,
                },
            },
            timeout=max(settings.timeout_seconds, 120),
        )
        self._raise_for_error(response, "Gemini analysis request failed")
        payload = self._parse_json(response, "Gemini analysis response returned invalid JSON")
        text = self._extract_response_text(payload)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiAnalysisError(f"Gemini returned malformed JSON text: {exc}") from exc
        if not isinstance(parsed, dict):
            raise GeminiAnalysisError("Gemini structured output did not return a JSON object.")
        return parsed

    def _delete_file(self, api_key: str, settings: GeminiSettings, file_name: str) -> bool:
        if self._session is None:
            return False
        try:
            response = self._session.request(
                "DELETE",
                f"{self._api_root(settings)}/{file_name}",
                headers={"x-goog-api-key": api_key.strip()},
                timeout=60,
            )
        except Exception:
            return False
        return 200 <= int(getattr(response, "status_code", 0) or 0) < 300

    def _build_analysis_prompt(self, timeline_context: ResolveTimelineContext) -> str:
        marker_lines = []
        if timeline_context.markers:
            for index, marker in enumerate(timeline_context.markers, start=1):
                marker_lines.append(
                    f"{index}. {marker.timestamp} | name={marker.name or 'Untitled'} | "
                    f"color={marker.color or 'None'} | note={marker.note or 'None'}"
                )
        else:
            marker_lines.append("No editorial markers were provided.")

        return (
            "Analyze this edited video and plan music prompts for a downstream soundtrack generator.\n\n"
            f"Project: {timeline_context.project_name}\n"
            f"Timeline: {timeline_context.timeline_name}\n"
            f"Frame rate: {timeline_context.frame_rate:.3f}\n"
            f"Relative duration seconds: {timeline_context.duration_seconds:.3f}\n"
            f"Timeline start timecode in Resolve: {timeline_context.start_timecode}\n\n"
            "Markers (all timestamps are relative to the uploaded preview):\n"
            + "\n".join(marker_lines)
            + "\n\nReturn a compact but production-ready music plan:\n"
            "- timeline_summary: 2-4 sentences about pacing, emotional arc, and edit rhythm.\n"
            "- base_music_prompt: the initial soundtrack prompt for the opening section.\n"
            "- extend_prompts: one item per important musical change, usually aligned to markers.\n"
            "- mix_notes: short bullet-style notes for arrangement, dynamics, and transitions.\n"
            "Use timestamps in HH:MM:SS.mmm format. Keep prompts concise and directly usable for music generation."
        )

    def _validate_plan(self, plan: GeminiMusicPromptPlan) -> None:
        if not plan.base_music_prompt.strip():
            raise GeminiAnalysisError("Gemini analysis did not include a base music prompt.")
        if not plan.timeline_summary.strip():
            raise GeminiAnalysisError("Gemini analysis did not include a timeline summary.")

    def _extract_response_text(self, payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise GeminiAnalysisError("Gemini response did not include any candidates.")
        first_candidate = candidates[0] if isinstance(candidates[0], dict) else {}
        content = first_candidate.get("content")
        if not isinstance(content, dict):
            raise GeminiAnalysisError("Gemini response candidate was missing content.")
        parts = content.get("parts")
        if not isinstance(parts, list):
            raise GeminiAnalysisError("Gemini response content did not include parts.")
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return str(part["text"])
        raise GeminiAnalysisError("Gemini response did not include any text parts.")

    def _parse_json(self, response: Any, message: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            raise GeminiAnalysisError(f"{message}: {exc}") from exc
        if not isinstance(payload, dict):
            raise GeminiAnalysisError(message)
        return payload

    def _raise_for_error(self, response: Any, message: str) -> None:
        status_code = int(getattr(response, "status_code", 0) or 0)
        if 200 <= status_code < 300:
            return
        body = getattr(response, "text", "")
        raise GeminiAnalysisError(f"{message} (HTTP {status_code}): {body[:240]}")

    def _emit_progress(self, progress_callback, update: GeminiAnalysisProgressUpdate) -> None:
        if callable(progress_callback):
            progress_callback(update)

    def _build_session(self) -> HTTPSession | None:
        return build_http_session()

    def _extract_file_payload(self, payload: dict[str, Any], error_message: str) -> dict[str, Any]:
        file_payload = payload.get("file")
        if isinstance(file_payload, dict):
            return file_payload
        state = payload.get("state")
        name = payload.get("name")
        uri = payload.get("uri")
        if isinstance(state, str) or isinstance(name, str) or isinstance(uri, str):
            return payload
        raise GeminiAnalysisError(error_message)

    def _api_root(self, settings: GeminiSettings) -> str:
        endpoint = settings.endpoint.rstrip("/")
        models_fragment = "/models"
        index = endpoint.find(models_fragment)
        if index >= 0:
            return endpoint[:index]
        return endpoint

    def _upload_files_url(self, settings: GeminiSettings) -> str:
        api_root = self._api_root(settings)
        split = urlsplit(api_root)
        upload_path = f"/upload{split.path.rstrip('/')}/files"
        return urlunsplit((split.scheme, split.netloc, upload_path, "", ""))


def _music_plan_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "timeline_summary": {
                "type": "string",
                "description": "A concise summary of the video's pacing, energy arc, and musical needs.",
            },
            "base_music_prompt": {
                "type": "string",
                "description": "The initial soundtrack generation prompt for the opening section.",
            },
            "extend_prompts": {
                "type": "array",
                "description": "Music changes or extension prompts tied to important scene changes or markers.",
                "items": {
                    "type": "object",
                    "properties": {
                        "timestamp": {
                            "type": "string",
                            "description": "Relative timestamp in HH:MM:SS.mmm format.",
                        },
                        "marker_name": {
                            "type": "string",
                            "description": "The matching marker name or a brief inferred scene label.",
                        },
                        "marker_note": {
                            "type": "string",
                            "description": "The user-provided marker note or an empty string if unavailable.",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "A concise extension prompt for the music model.",
                        },
                        "transition_goal": {
                            "type": "string",
                            "description": "What should change musically at this beat.",
                        },
                    },
                    "required": ["timestamp", "marker_name", "marker_note", "prompt", "transition_goal"],
                    "additionalProperties": False,
                },
            },
            "mix_notes": {
                "type": "array",
                "description": "Short notes about dynamics, transitions, arrangement, or edit sensitivity.",
                "items": {"type": "string"},
            },
        },
        "required": ["timeline_summary", "base_music_prompt", "extend_prompts", "mix_notes"],
        "additionalProperties": False,
    }
