from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Mapping

from cinescore_ai.paths import get_config_file_path, get_default_output_directory, get_default_temp_directory


def _nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass(slots=True)
class GeminiSettings:
    model: str = "gemini-2.5-flash"
    endpoint: str = "https://generativelanguage.googleapis.com/v1beta/models"
    timeout_seconds: int = 45


@dataclass(slots=True)
class GeminiMusicSettings:
    model: str = "lyria-3-pro-preview"
    vocals_mode: str = "instrumental"
    output_format: str = "mp3"
    use_marker_images: bool = True
    max_images: int = 10
    crossfade_seconds: float = 2.0


@dataclass(slots=True)
class AudioProviderSettings:
    provider_name: str = "aimlapi"
    base_url: str = "https://api.aimlapi.com/v1"
    model_hint: str = "stable-audio"
    test_endpoint: str = "/models"
    timeout_seconds: int = 90


@dataclass(slots=True)
class PathSettings:
    output_directory: str = field(default_factory=lambda: str(get_default_output_directory()))
    temp_directory: str = field(default_factory=lambda: str(get_default_temp_directory()))
    temp_preview_retention_days: int = 14


@dataclass(slots=True)
class UISettings:
    window_width: int = 980
    window_height: int = 760


@dataclass(slots=True)
class AppConfig:
    active_audio_provider: str = "aimlapi"
    gemini: GeminiSettings = field(default_factory=GeminiSettings)
    gemini_music: GeminiMusicSettings = field(default_factory=GeminiMusicSettings)
    audio_provider: AudioProviderSettings = field(default_factory=AudioProviderSettings)
    paths: PathSettings = field(default_factory=PathSettings)
    ui: UISettings = field(default_factory=UISettings)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AppConfig":
        gemini_data = _nested_dict(data.get("gemini"))
        gemini_music_data = _nested_dict(data.get("gemini_music"))
        audio_data = _nested_dict(data.get("audio_provider"))
        path_data = _nested_dict(data.get("paths"))
        ui_data = _nested_dict(data.get("ui"))
        active_audio_provider = str(data.get("active_audio_provider", "aimlapi"))
        audio_provider_name = str(audio_data.get("provider_name", active_audio_provider or "aimlapi"))
        audio_defaults = get_default_audio_provider_settings(audio_provider_name)
        return cls(
            active_audio_provider=active_audio_provider,
            gemini=GeminiSettings(
                model=str(gemini_data.get("model", GeminiSettings.model)),
                endpoint=str(gemini_data.get("endpoint", GeminiSettings.endpoint)),
                timeout_seconds=int(gemini_data.get("timeout_seconds", GeminiSettings.timeout_seconds)),
            ),
            gemini_music=GeminiMusicSettings(
                model=str(gemini_music_data.get("model", GeminiMusicSettings.model)),
                vocals_mode=str(gemini_music_data.get("vocals_mode", GeminiMusicSettings.vocals_mode)),
                output_format=str(gemini_music_data.get("output_format", GeminiMusicSettings.output_format)),
                use_marker_images=bool(gemini_music_data.get("use_marker_images", GeminiMusicSettings.use_marker_images)),
                max_images=int(gemini_music_data.get("max_images", GeminiMusicSettings.max_images)),
                crossfade_seconds=float(
                    gemini_music_data.get("crossfade_seconds", GeminiMusicSettings.crossfade_seconds)
                ),
            ),
            audio_provider=AudioProviderSettings(
                provider_name=str(audio_data.get("provider_name", audio_defaults.provider_name)),
                base_url=str(audio_data.get("base_url", audio_defaults.base_url)),
                model_hint=str(audio_data.get("model_hint", audio_defaults.model_hint)),
                test_endpoint=str(audio_data.get("test_endpoint", audio_defaults.test_endpoint)),
                timeout_seconds=int(audio_data.get("timeout_seconds", audio_defaults.timeout_seconds)),
            ),
            paths=PathSettings(
                output_directory=str(path_data.get("output_directory", get_default_output_directory())),
                temp_directory=str(path_data.get("temp_directory", get_default_temp_directory())),
                temp_preview_retention_days=int(path_data.get("temp_preview_retention_days", 14)),
            ),
            ui=UISettings(
                window_width=int(ui_data.get("window_width", UISettings.window_width)),
                window_height=int(ui_data.get("window_height", UISettings.window_height)),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_default_audio_provider_settings(provider_name: str) -> AudioProviderSettings:
    normalized = provider_name.strip().lower()
    if normalized == "sunoapi":
        return AudioProviderSettings(
            provider_name="sunoapi",
            base_url="https://api.sunoapi.org/api/v1",
            model_hint="V4_5ALL",
            test_endpoint="/generate/credit",
            timeout_seconds=90,
        )
    return AudioProviderSettings(
        provider_name="aimlapi",
        base_url="https://api.aimlapi.com/v1",
        model_hint="stable-audio",
        test_endpoint="/models",
        timeout_seconds=90,
    )


class AppConfigStore:
    def __init__(self, config_file_path: Path | None = None) -> None:
        self.config_file_path = config_file_path or get_config_file_path()

    def load(self) -> AppConfig:
        if not self.config_file_path.exists():
            return AppConfig()
        try:
            raw_data = json.loads(self.config_file_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError, TypeError, ValueError):
            return AppConfig()
        if not isinstance(raw_data, dict):
            return AppConfig()
        return AppConfig.from_dict(raw_data)

    def save(self, config: AppConfig) -> None:
        self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(config.to_dict(), indent=2, sort_keys=True)
        self.config_file_path.write_text(serialized + "\n", encoding="utf-8")
