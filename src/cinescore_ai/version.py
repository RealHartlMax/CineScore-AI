from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def get_app_version() -> str:
    try:
        return version("cinescore-ai")
    except PackageNotFoundError:
        return "0.1.2d"


__version__ = get_app_version()