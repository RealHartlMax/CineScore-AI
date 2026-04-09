from __future__ import annotations

import unittest

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.config import AudioProviderSettings
from cinescore_ai.providers import SunoApiAudioProvider


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

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


class SunoApiAudioProviderTests(unittest.TestCase):
    def test_start_generation_and_fetch_status(self) -> None:
        provider = SunoApiAudioProvider()
        session = _QueuedSession(
            [
                _FakeResponse(200, {"code": 200, "msg": "success", "data": {"taskId": "task-123"}}),
                _FakeResponse(
                    200,
                    {
                        "code": 200,
                        "msg": "success",
                        "data": {
                            "taskId": "task-123",
                            "status": "SUCCESS",
                            "response": {
                                "sunoData": [
                                    {"audioUrl": "https://cdn.suno.example/result.mp3"},
                                    {"audioUrl": "https://cdn.suno.example/result-2.mp3"},
                                ]
                            },
                        },
                    },
                ),
            ]
        )
        settings = AudioProviderSettings(
            provider_name="sunoapi",
            base_url="https://api.sunoapi.org/api/v1",
            model_hint="V4_5ALL",
        )

        started = provider.start_generation(
            api_key="secret",
            settings=settings,
            prompt="A calm cinematic piano pulse.",
            duration_seconds=12,
            session=session,
        )
        status = provider.get_generation_status(
            api_key="secret",
            settings=settings,
            generation_id=started.generation_id,
            session=session,
        )

        self.assertEqual(started.generation_id, "task-123")
        self.assertEqual(started.status, "pending")
        self.assertEqual(status.status, "completed")
        self.assertEqual(status.audio_url, "https://cdn.suno.example/result.mp3")
        self.assertEqual(session.calls[0][1], "https://api.sunoapi.org/api/v1/generate")
        self.assertEqual(session.calls[1][1], "https://api.sunoapi.org/api/v1/generate/record-info")
        self.assertEqual(session.calls[1][2]["params"], {"taskId": "task-123"})

        request_body = session.calls[0][2]["json"]
        self.assertEqual(request_body["customMode"], False)
        self.assertEqual(request_body["instrumental"], True)
        self.assertEqual(request_body["model"], "V4_5ALL")
