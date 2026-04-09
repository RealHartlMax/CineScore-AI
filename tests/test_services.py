from __future__ import annotations

import unittest

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.config import AudioProviderSettings, GeminiSettings
from cinescore_ai.services import ConnectionTestService


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


class ConnectionTestServiceTests(unittest.TestCase):
    def test_gemini_connection_reports_matching_model(self) -> None:
        session = _FakeSession(
            _FakeResponse(
                200,
                {
                    "models": [
                        {"name": "models/gemini-2.5-flash"},
                        {"name": "models/lyria-3-pro-preview"},
                        {"name": "models/other"},
                    ]
                },
            )
        )
        service = ConnectionTestService(session=session)

        result = service.test_gemini(
            api_key="secret",
            settings=GeminiSettings(model="gemini-2.5-flash", endpoint="https://gemini.example/models"),
        )

        self.assertTrue(result.ok)
        self.assertIn("gemini-2.5-flash", result.message)
        self.assertEqual(result.details["analysis_models"], ["gemini-2.5-flash"])
        self.assertEqual(result.details["music_models"], ["lyria-3-pro-preview"])
        self.assertEqual(session.calls[0][1], "https://gemini.example/models")

    def test_audio_provider_reports_auth_failure(self) -> None:
        session = _FakeSession(_FakeResponse(401, {}, text="unauthorized"))
        service = ConnectionTestService(session=session)

        result = service.test_audio_provider(
            api_key="secret",
            settings=AudioProviderSettings(base_url="https://aiml.example/v1", test_endpoint="/models"),
        )

        self.assertFalse(result.ok)
        self.assertIn("authentication failed", result.message.lower())
        self.assertEqual(session.calls[0][1], "https://aiml.example/v1/models")

    def test_sunoapi_connection_reports_remaining_credits(self) -> None:
        session = _FakeSession(_FakeResponse(200, {"code": 200, "msg": "success", "data": 42}))
        service = ConnectionTestService(session=session)

        result = service.test_audio_provider(
            api_key="secret",
            settings=AudioProviderSettings(
                provider_name="sunoapi",
                base_url="https://api.sunoapi.org/api/v1",
                model_hint="V4_5ALL",
                test_endpoint="/generate/credit",
            ),
        )

        self.assertTrue(result.ok)
        self.assertIn("42", result.message)
        self.assertEqual(session.calls[0][1], "https://api.sunoapi.org/api/v1/generate/credit")
