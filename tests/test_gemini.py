from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.config import GeminiSettings
from cinescore_ai.gemini import GeminiAnalysisError, GeminiVideoAnalysisService
from cinescore_ai.resolve import MockResolveAdapter


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        *,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.headers = headers or {}

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


class GeminiVideoAnalysisServiceTests(unittest.TestCase):
    def test_analyze_preview_uploads_generates_and_cleans_up(self) -> None:
        analysis_payload = {
            "timeline_summary": "The cut opens restrained, then grows brighter and wider before a bold reveal.",
            "base_music_prompt": "Warm cinematic pulses with light piano and restrained percussion.",
            "extend_prompts": [
                {
                    "timestamp": "00:00:10.000",
                    "marker_name": "Lift",
                    "marker_note": "Build into a more cinematic groove here.",
                    "prompt": "Introduce fuller drums and wider strings without losing momentum.",
                    "transition_goal": "Increase scale and forward motion.",
                }
            ],
            "mix_notes": [
                "Keep dialogue space open in the opening.",
                "Hit the reveal with a stronger low-end accent.",
            ],
        }
        session = _QueuedSession(
            [
                _FakeResponse(
                    200,
                    {},
                    headers={"X-Goog-Upload-URL": "https://upload.example/session"},
                ),
                _FakeResponse(
                    200,
                    {"file": {"name": "files/mock-file", "uri": "https://files.example/mock-file", "state": "PROCESSING"}},
                ),
                _FakeResponse(
                    200,
                    {"file": {"name": "files/mock-file", "uri": "https://files.example/mock-file", "state": "ACTIVE"}},
                ),
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "text": json.dumps(analysis_payload),
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                ),
                _FakeResponse(204, {}),
            ]
        )
        service = GeminiVideoAnalysisService(session=session)
        settings = GeminiSettings(
            model="gemini-2.5-flash",
            endpoint="https://gemini.example/v1beta/models",
            timeout_seconds=30,
        )
        context = MockResolveAdapter().get_current_timeline_context()
        progress_updates = []

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"fake mp4 bytes")

            result = service.analyze_preview(
                api_key="secret",
                settings=settings,
                timeline_context=context,
                preview_path=preview_path,
                progress_callback=progress_updates.append,
            )

        self.assertEqual(result.preview_path, str(preview_path))
        self.assertEqual(result.remote_file_name, "files/mock-file")
        self.assertTrue(result.remote_cleanup_attempted)
        self.assertTrue(result.remote_cleanup_succeeded)
        self.assertEqual(result.plan.base_music_prompt, analysis_payload["base_music_prompt"])
        self.assertEqual(result.plan.extend_prompts[0].marker_name, "Lift")
        self.assertEqual(
            [update.phase for update in progress_updates],
            ["preparing", "uploaded", "processing", "generating", "generated", "cleanup"],
        )

        self.assertEqual(session.calls[0][0], "POST")
        self.assertEqual(session.calls[0][1], "https://gemini.example/upload/v1beta/files")
        self.assertEqual(session.calls[2][1], "https://gemini.example/v1beta/files/mock-file")
        self.assertEqual(session.calls[3][1], "https://gemini.example/v1beta/models/gemini-2.5-flash:generateContent")
        self.assertEqual(session.calls[4][1], "https://gemini.example/v1beta/files/mock-file")

        request_body = session.calls[3][2]["json"]
        content_parts = request_body["contents"][0]["parts"]
        self.assertEqual(content_parts[0]["file_data"]["mime_type"], "video/mp4")
        self.assertEqual(content_parts[0]["file_data"]["file_uri"], "https://files.example/mock-file")

    def test_analyze_preview_requires_api_key(self) -> None:
        service = GeminiVideoAnalysisService(session=_QueuedSession([]))
        settings = GeminiSettings()
        context = MockResolveAdapter().get_current_timeline_context()

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"fake mp4 bytes")

            with self.assertRaises(GeminiAnalysisError):
                service.analyze_preview(
                    api_key="",
                    settings=settings,
                    timeline_context=context,
                    preview_path=preview_path,
                )
