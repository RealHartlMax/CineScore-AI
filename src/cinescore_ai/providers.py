from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from cinescore_ai.config import AudioProviderSettings


class HTTPSession(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        ...


@dataclass(slots=True)
class ConnectionTestResult:
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AudioGenerationStatus:
    generation_id: str
    status: str
    audio_url: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class AudioProvider(ABC):
    provider_name: str
    display_name: str

    @abstractmethod
    def test_connection(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        session: HTTPSession,
    ) -> ConnectionTestResult:
        raise NotImplementedError

    @abstractmethod
    def start_generation(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        prompt: str,
        duration_seconds: int,
        session: HTTPSession,
    ) -> AudioGenerationStatus:
        raise NotImplementedError

    @abstractmethod
    def get_generation_status(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        generation_id: str,
        session: HTTPSession,
    ) -> AudioGenerationStatus:
        raise NotImplementedError


class AimlApiAudioProvider(AudioProvider):
    provider_name = "aimlapi"
    display_name = "AIMLAPI-Compatible"

    def test_connection(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        session: HTTPSession,
    ) -> ConnectionTestResult:
        if not api_key.strip():
            return ConnectionTestResult(ok=False, message="Audio provider API key is required.")

        url = f"{settings.base_url.rstrip('/')}/{settings.test_endpoint.lstrip('/')}"
        response = session.request(
            "GET",
            url,
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            timeout=settings.timeout_seconds,
        )

        if response.status_code == 401:
            return ConnectionTestResult(ok=False, message="Audio provider authentication failed.")
        if response.status_code >= 400:
            return ConnectionTestResult(
                ok=False,
                message=f"Audio provider test failed with HTTP {response.status_code}.",
                details={"body": getattr(response, "text", "")[:240]},
            )

        payload = response.json()
        models = payload.get("data", payload)
        return ConnectionTestResult(
            ok=True,
            message="Audio provider connection succeeded.",
            details={"models_preview": models[:3] if isinstance(models, list) else payload},
        )

    def start_generation(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        prompt: str,
        duration_seconds: int,
        session: HTTPSession,
    ) -> AudioGenerationStatus:
        if not api_key.strip():
            raise RuntimeError("Audio provider API key is required.")
        if not prompt.strip():
            raise RuntimeError("Audio generation prompt is required.")

        response = session.request(
            "POST",
            self._generation_url(settings),
            headers=self._build_headers(api_key),
            json={
                "model": settings.model_hint.strip(),
                "prompt": prompt.strip(),
                "seconds_total": int(duration_seconds),
            },
            timeout=max(settings.timeout_seconds, 60),
        )
        return self._parse_generation_response(response, "Audio generation request failed")

    def get_generation_status(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        generation_id: str,
        session: HTTPSession,
    ) -> AudioGenerationStatus:
        if not api_key.strip():
            raise RuntimeError("Audio provider API key is required.")
        if not generation_id.strip():
            raise RuntimeError("Audio generation id is required.")

        response = session.request(
            "GET",
            self._generation_url(settings),
            headers=self._build_headers(api_key),
            params={"generation_id": generation_id.strip()},
            timeout=max(settings.timeout_seconds, 60),
        )
        return self._parse_generation_response(response, "Audio generation status lookup failed")

    def _parse_generation_response(self, response: Any, message: str) -> AudioGenerationStatus:
        if int(getattr(response, "status_code", 0) or 0) >= 400:
            body = getattr(response, "text", "")[:240]
            raise RuntimeError(f"{message} (HTTP {response.status_code}): {body}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"{message}: response body was not a JSON object.")

        generation_id = str(payload.get("id", "")).strip()
        status = str(payload.get("status", "")).strip()
        if not generation_id or not status:
            raise RuntimeError(f"{message}: generation id or status was missing.")

        audio_file = payload.get("audio_file")
        audio_url = None
        if isinstance(audio_file, dict):
            candidate = audio_file.get("url")
            if candidate:
                audio_url = str(candidate)

        error = payload.get("error")
        error_message = None
        if isinstance(error, dict):
            for key in ("message", "detail", "description", "error"):
                candidate = error.get(key)
                if candidate:
                    error_message = str(candidate)
                    break
        elif error:
            error_message = str(error)

        return AudioGenerationStatus(
            generation_id=generation_id,
            status=status,
            audio_url=audio_url,
            error_message=error_message,
            raw=payload,
        )

    def _build_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key.strip()}"}

    def _generation_url(self, settings: AudioProviderSettings) -> str:
        split = urlsplit(settings.base_url.rstrip("/"))
        path = split.path.rstrip("/")
        if path.endswith("/v1") or path.endswith("/v2"):
            path = path[:-3]
        generation_path = f"{path}/v2/generate/audio"
        return urlunsplit((split.scheme, split.netloc, generation_path, "", ""))


class SunoApiAudioProvider(AudioProvider):
    provider_name = "sunoapi"
    display_name = "SunoAPI"

    def test_connection(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        session: HTTPSession,
    ) -> ConnectionTestResult:
        if not api_key.strip():
            return ConnectionTestResult(ok=False, message="Audio provider API key is required.")

        response = session.request(
            "GET",
            self._credits_url(settings),
            headers=self._build_headers(api_key),
            timeout=settings.timeout_seconds,
        )

        if response.status_code == 401:
            return ConnectionTestResult(ok=False, message="SunoAPI authentication failed.")
        if response.status_code >= 400:
            return ConnectionTestResult(
                ok=False,
                message=f"SunoAPI connection test failed with HTTP {response.status_code}.",
                details={"body": getattr(response, "text", "")[:240]},
            )

        payload = response.json()
        if not isinstance(payload, dict):
            return ConnectionTestResult(ok=False, message="SunoAPI returned invalid JSON.")
        if int(payload.get("code", 0) or 0) != 200:
            return ConnectionTestResult(
                ok=False,
                message=f"SunoAPI connection test failed: {payload.get('msg', 'unknown error')}.",
                details={"payload": payload},
            )

        credits = payload.get("data")
        return ConnectionTestResult(
            ok=True,
            message=f"SunoAPI connection succeeded. Remaining credits: {credits}.",
            details={"credits": credits},
        )

    def start_generation(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        prompt: str,
        duration_seconds: int,
        session: HTTPSession,
    ) -> AudioGenerationStatus:
        if not api_key.strip():
            raise RuntimeError("Audio provider API key is required.")
        if not prompt.strip():
            raise RuntimeError("Audio generation prompt is required.")

        response = session.request(
            "POST",
            self._generate_url(settings),
            headers=self._json_headers(api_key),
            json={
                "prompt": prompt.strip(),
                "customMode": False,
                "instrumental": True,
                "model": self._resolve_model(settings),
            },
            timeout=max(settings.timeout_seconds, 60),
        )
        if int(getattr(response, "status_code", 0) or 0) >= 400:
            body = getattr(response, "text", "")[:240]
            raise RuntimeError(f"SunoAPI generation request failed (HTTP {response.status_code}): {body}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("SunoAPI generation request returned invalid JSON.")
        if int(payload.get("code", 0) or 0) != 200:
            raise RuntimeError(f"SunoAPI generation request failed: {payload.get('msg', 'unknown error')}")

        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("taskId"):
            raise RuntimeError("SunoAPI generation request did not return a taskId.")

        return AudioGenerationStatus(
            generation_id=str(data["taskId"]),
            status="pending",
            raw=payload,
        )

    def get_generation_status(
        self,
        api_key: str,
        settings: AudioProviderSettings,
        generation_id: str,
        session: HTTPSession,
    ) -> AudioGenerationStatus:
        if not api_key.strip():
            raise RuntimeError("Audio provider API key is required.")
        if not generation_id.strip():
            raise RuntimeError("Audio generation id is required.")

        response = session.request(
            "GET",
            self._record_info_url(settings),
            headers=self._build_headers(api_key),
            params={"taskId": generation_id.strip()},
            timeout=max(settings.timeout_seconds, 60),
        )
        if int(getattr(response, "status_code", 0) or 0) >= 400:
            body = getattr(response, "text", "")[:240]
            raise RuntimeError(f"SunoAPI generation status lookup failed (HTTP {response.status_code}): {body}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("SunoAPI generation status returned invalid JSON.")
        if int(payload.get("code", 0) or 0) != 200:
            raise RuntimeError(f"SunoAPI generation status failed: {payload.get('msg', 'unknown error')}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("SunoAPI generation status response did not include task data.")

        source_status = str(data.get("status", "PENDING")).strip().upper()
        error_message = data.get("errorMessage")
        if error_message is not None:
            error_message = str(error_message)

        response_data = data.get("response")
        audio_url = None
        if isinstance(response_data, dict):
            suno_data = response_data.get("sunoData")
            if isinstance(suno_data, list) and suno_data:
                first_track = suno_data[0] if isinstance(suno_data[0], dict) else {}
                candidate_url = first_track.get("audioUrl")
                if candidate_url:
                    audio_url = str(candidate_url)

        return AudioGenerationStatus(
            generation_id=generation_id.strip(),
            status=self._normalize_status(source_status),
            audio_url=audio_url,
            error_message=error_message,
            raw=payload,
        )

    def _normalize_status(self, source_status: str) -> str:
        if source_status == "SUCCESS":
            return "completed"
        if source_status in {"CREATE_TASK_FAILED", "GENERATE_AUDIO_FAILED", "CALLBACK_EXCEPTION", "SENSITIVE_WORD_ERROR"}:
            return "failed"
        return "pending"

    def _resolve_model(self, settings: AudioProviderSettings) -> str:
        model = settings.model_hint.strip()
        return model if model else "V4_5ALL"

    def _build_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key.strip()}"}

    def _json_headers(self, api_key: str) -> dict[str, str]:
        headers = self._build_headers(api_key)
        headers["Content-Type"] = "application/json"
        return headers

    def _credits_url(self, settings: AudioProviderSettings) -> str:
        return f"{self._api_root(settings)}/generate/credit"

    def _generate_url(self, settings: AudioProviderSettings) -> str:
        return f"{self._api_root(settings)}/generate"

    def _record_info_url(self, settings: AudioProviderSettings) -> str:
        return f"{self._api_root(settings)}/generate/record-info"

    def _api_root(self, settings: AudioProviderSettings) -> str:
        base_url = settings.base_url.rstrip("/")
        split = urlsplit(base_url)
        path = split.path.rstrip("/")
        if path.endswith("/generate"):
            path = path[: -len("/generate")]
        elif path.endswith("/generate/credit"):
            path = path[: -len("/generate/credit")]
        elif path.endswith("/generate/record-info"):
            path = path[: -len("/generate/record-info")]
        elif not path.endswith("/api/v1"):
            path = f"{path}/api/v1" if path else "/api/v1"
        return urlunsplit((split.scheme, split.netloc, path, "", ""))


def get_audio_provider(provider_name: str) -> AudioProvider:
    normalized = provider_name.strip().lower()
    if normalized == AimlApiAudioProvider.provider_name:
        return AimlApiAudioProvider()
    if normalized == SunoApiAudioProvider.provider_name:
        return SunoApiAudioProvider()
    raise ValueError(f"Unsupported audio provider '{provider_name}'.")
