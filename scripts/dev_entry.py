from __future__ import annotations

import inspect
import sys
from pathlib import Path


def _iter_search_roots() -> list[Path]:
    candidates: list[Path] = []

    file_name = globals().get("__file__")
    if isinstance(file_name, str) and file_name:
        candidates.append(Path(file_name))

    source_file = inspect.getsourcefile(_bootstrap_src_path)
    if source_file:
        candidates.append(Path(source_file))

    if sys.argv and sys.argv[0]:
        candidates.append(Path(sys.argv[0]))

    candidates.append(Path.cwd())
    candidates.extend(Path(entry) for entry in sys.path if entry)

    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        search_root = resolved if resolved.is_dir() else resolved.parent
        for root in (search_root, *search_root.parents):
            key = str(root).lower()
            if key in seen:
                continue
            seen.add(key)
            roots.append(root)
    return roots


def _bootstrap_src_path() -> None:
    for root in _iter_search_roots():
        src_dir = root / "src"
        app_module = src_dir / "cinescore_ai" / "app.py"
        if not app_module.exists():
            continue
        src_dir_str = str(src_dir)
        if src_dir_str not in sys.path:
            sys.path.insert(0, src_dir_str)
        return

    raise RuntimeError(
        "Could not locate the CineScore-AI 'src' directory. "
        "Install the full project folder next to this launcher so it contains 'src/cinescore_ai/app.py'."
    )


_bootstrap_src_path()

from cinescore_ai.app import launch_app
from cinescore_ai.resolve import MockResolveAdapter


if __name__ == "__main__":
    launch_app(resolve_adapter=MockResolveAdapter(), block=True)
