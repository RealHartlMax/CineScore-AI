from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.audio import AudioWorkflowService
from cinescore_ai.config import AudioProviderSettings
from cinescore_ai.gemini import (
    GeminiExtendPromptPlan,
    GeminiMusicPromptPlan,
    GeminiVideoAnalysisResult,
)
from cinescore_ai.resolve import MockResolveAdapter


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        *,
        text: str = "",
        content: bytes | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")

    def json(self) -> dict:
        return self._payload


class _QueuedSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self._responses:
            raise AssertionError(f"Unexpected request: {method} {url}")
        return self._responses.pop(0)


class AudioWorkflowServiceTests(unittest.TestCase):
    def test_compose_from_analysis_generates_downloads_and_places_audio(self) -> None:
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        analysis_result = GeminiVideoAnalysisResult(
            preview_path="preview.mp4",
            remote_file_name="files/mock",
            remote_file_uri="https://files.example/mock",
            remote_cleanup_attempted=True,
            remote_cleanup_succeeded=True,
            plan=GeminiMusicPromptPlan(
                timeline_summary="Starts gentle, then grows into a brighter reveal.",
                base_music_prompt="Soft pulses and warm piano.",
                extend_prompts=[
                    GeminiExtendPromptPlan(
                        timestamp="00:00:10.000",
                        marker_name="Lift",
                        marker_note="Build into a more cinematic groove here.",
                        prompt="Add wider drums and brighter synth motion.",
                        transition_goal="Raise energy and width.",
                    )
                ],
                mix_notes=["Leave space for dialogue."],
            ),
            raw_json={},
        )
        session = _QueuedSession(
            [
                _FakeResponse(200, {"id": "gen-base", "status": "queued"}),
                _FakeResponse(
                    200,
                    {
                        "id": "gen-base",
                        "status": "completed",
                        "audio_file": {"url": "https://cdn.example/base.mp3"},
                    },
                ),
                _FakeResponse(200, content=b"base-audio"),
                _FakeResponse(200, {"id": "gen-lift", "status": "queued"}),
                _FakeResponse(
                    200,
                    {
                        "id": "gen-lift",
                        "status": "completed",
                        "audio_file": {"url": "https://cdn.example/lift.mp3"},
                    },
                ),
                _FakeResponse(200, content=b"lift-audio"),
            ]
        )
        service = AudioWorkflowService(resolve_adapter=adapter, session=session)
        progress_updates = []

        with TemporaryDirectory() as temp_dir:
            result = service.compose_from_analysis(
                api_key="secret",
                settings=AudioProviderSettings(
                    provider_name="aimlapi",
                    base_url="https://api.aiml.example/v1",
                    model_hint="stable-audio",
                    timeout_seconds=30,
                ),
                timeline_context=context,
                analysis_result=analysis_result,
                output_directory=temp_dir,
                progress_callback=progress_updates.append,
                poll_interval_seconds=0.0,
                timeout_seconds=1.0,
            )

            self.assertEqual(result.track_index, 4)
            self.assertEqual(len(result.segments), 2)
            self.assertTrue(Path(result.segments[0].file_path).exists())
            self.assertTrue(Path(result.segments[1].file_path).exists())
            self.assertEqual(result.segments[0].placement.record_frame, context.start_frame)
            self.assertEqual(result.segments[1].placement.record_frame, context.start_frame + 240)
            self.assertEqual(result.segments[1].placement.track_index, 4)

        self.assertEqual(session.calls[0][1], "https://api.aiml.example/v2/generate/audio")
        self.assertEqual(session.calls[1][1], "https://api.aiml.example/v2/generate/audio")
        self.assertEqual(session.calls[2][1], "https://cdn.example/base.mp3")
        self.assertEqual(session.calls[3][1], "https://api.aiml.example/v2/generate/audio")
        self.assertEqual(session.calls[4][1], "https://api.aiml.example/v2/generate/audio")
        self.assertEqual(session.calls[5][1], "https://cdn.example/lift.mp3")
        self.assertIn("Using Resolve audio track 4", progress_updates[0].message)
        self.assertEqual(result.segments[0].plan.duration_seconds, 10)
        self.assertEqual(result.segments[1].plan.duration_seconds, 20)
