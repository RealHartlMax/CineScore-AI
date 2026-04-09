from __future__ import annotations

from cinescore_ai.config import AudioProviderSettings, GeminiSettings
from cinescore_ai.http_client import build_http_session
from cinescore_ai.providers import ConnectionTestResult, HTTPSession, get_audio_provider


class ConnectionTestService:
    def __init__(self, session: HTTPSession | None = None) -> None:
        self._session = session or self._build_session()

    def test_gemini(self, api_key: str, settings: GeminiSettings) -> ConnectionTestResult:
        if self._session is None:
            return ConnectionTestResult(ok=False, message="No HTTP client is available.")
        if not api_key.strip():
            return ConnectionTestResult(ok=False, message="Gemini API key is required.")

        response_or_error = self._fetch_gemini_models(api_key=api_key, settings=settings)
        if isinstance(response_or_error, ConnectionTestResult):
            return response_or_error
        response = response_or_error

        if response.status_code == 401:
            return ConnectionTestResult(ok=False, message="Gemini authentication failed.")
        if response.status_code >= 400:
            return ConnectionTestResult(
                ok=False,
                message=f"Gemini connection test failed with HTTP {response.status_code}.",
                details={"body": getattr(response, "text", "")[:240]},
            )

        try:
            payload = response.json()
        except Exception as exc:
            return ConnectionTestResult(ok=False, message=f"Gemini returned invalid JSON: {exc}")
        models = payload.get("models", [])
        analysis_models = self._collect_model_names(models, prefixes=("models/gemini-",))
        music_models = self._collect_model_names(models, prefixes=("models/lyria-",))
        matched_model = next(
            (model.get("name", "") for model in models if settings.model in model.get("name", "")),
            None,
        )
        if matched_model:
            return ConnectionTestResult(
                ok=True,
                message=(
                    f"Gemini connection succeeded and found '{matched_model}'. "
                    f"Loaded {len(analysis_models)} Gemini model(s) and {len(music_models)} music model(s)."
                ),
                details={
                    "analysis_models": analysis_models,
                    "music_models": music_models,
                },
            )
        return ConnectionTestResult(
            ok=True,
            message=(
                f"Gemini connection succeeded. Loaded {len(analysis_models)} Gemini model(s) "
                f"and {len(music_models)} music model(s)."
            ),
            details={
                "analysis_models": analysis_models,
                "music_models": music_models,
                "available_models_preview": [model.get("name", "") for model in models[:5]],
            },
        )

    def test_audio_provider(self, api_key: str, settings: AudioProviderSettings) -> ConnectionTestResult:
        if self._session is None:
            return ConnectionTestResult(ok=False, message="The 'requests' package is not installed.")
        provider = get_audio_provider(settings.provider_name)
        try:
            return provider.test_connection(
                api_key=api_key,
                settings=settings,
                session=self._session,
            )
        except Exception as exc:
            return ConnectionTestResult(ok=False, message=f"Audio provider test failed: {exc}")

    def _build_session(self) -> HTTPSession | None:
        return build_http_session()

    def _fetch_gemini_models(self, api_key: str, settings: GeminiSettings):
        try:
            return self._session.request(
                "GET",
                settings.endpoint.rstrip("/"),
                params={"key": api_key.strip()},
                timeout=settings.timeout_seconds,
            )
        except Exception as exc:
            return ConnectionTestResult(ok=False, message=f"Gemini connection test failed: {exc}")

    def _collect_model_names(self, models: object, prefixes: tuple[str, ...]) -> list[str]:
        collected: list[str] = []
        if not isinstance(models, list):
            return collected
        normalized_prefixes = tuple(prefix.lower() for prefix in prefixes)
        for model in models:
            if not isinstance(model, dict):
                continue
            name = str(model.get("name", "")).strip()
            if not name:
                continue
            normalized_name = name.lower()
            if not any(normalized_name.startswith(prefix) for prefix in normalized_prefixes):
                continue
            short_name = name.split("/", 1)[1] if "/" in name else name
            if short_name not in collected:
                collected.append(short_name)
        return collected
