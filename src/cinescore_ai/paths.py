from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from PySide6.QtCore import QStandardPaths
except ImportError:  # pragma: no cover - depends on local environment
    QStandardPaths = None  # type: ignore[assignment]

APP_NAME = "CineScore AI"
APP_SLUG = "CineScore-AI"


def _qt_location(location: int) -> Path | None:
    if QStandardPaths is None:
        return None
    value = QStandardPaths.writableLocation(location)
    if not value:
        return None
    return Path(value)


def _platform_config_root() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _platform_cache_root() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


def _platform_music_root() -> Path:
    if sys.platform.startswith("win"):
        return Path.home() / "Music"
    if sys.platform == "darwin":
        return Path.home() / "Music"
    return Path.home() / "Music"


def get_config_directory() -> Path:
    location = _qt_location(QStandardPaths.StandardLocation.AppConfigLocation) if QStandardPaths else None
    return location or (_platform_config_root() / APP_SLUG)


def get_cache_directory() -> Path:
    location = _qt_location(QStandardPaths.StandardLocation.CacheLocation) if QStandardPaths else None
    return location or (_platform_cache_root() / APP_SLUG)


def get_default_output_directory() -> Path:
    music_dir = _qt_location(QStandardPaths.StandardLocation.MusicLocation) if QStandardPaths else None
    return (music_dir or _platform_music_root()) / APP_NAME


def get_default_temp_directory() -> Path:
    return get_cache_directory() / "temp"


def get_config_file_path() -> Path:
    return get_config_directory() / "config.json"
