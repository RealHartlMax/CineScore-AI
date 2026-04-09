from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import sys
from pathlib import Path
from typing import Mapping

from cinescore_ai.paths import APP_NAME, get_config_directory


@dataclass(slots=True)
class ResolveInstallationResult:
    install_root: Path
    entry_script_path: Path
    launcher_path: Path
    copied_files: int


def get_resolve_scripts_directory(
    *,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    current_platform = platform or sys.platform
    current_env = dict(os.environ if env is None else env)

    if current_platform.startswith("win"):
        appdata = Path(current_env.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility"
    if current_platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Fusion"
            / "Scripts"
            / "Utility"
        )
    return Path.home() / ".local" / "share" / "DaVinciResolve" / "Fusion" / "Scripts" / "Utility"


def get_resolve_runtime_directory(config_directory: Path | None = None) -> Path:
    return (config_directory or get_config_directory()) / "resolve-runtime"


def render_resolve_launcher(entry_script_path: Path) -> str:
    normalized_entry = entry_script_path.resolve()
    return f'''from __future__ import annotations

import os
from pathlib import Path


ENTRY_SCRIPT = Path(os.environ.get("CINESCORE_AI_RESOLVE_ENTRY", r"{normalized_entry}"))

if not ENTRY_SCRIPT.exists():
    raise RuntimeError(
        "Could not find the installed CineScore AI Resolve entry script at "
        f"'{{ENTRY_SCRIPT}}'. Run the Resolve installer again."
    )

_launcher_globals = globals()
_launcher_globals["__file__"] = str(ENTRY_SCRIPT)
exec(compile(ENTRY_SCRIPT.read_text(encoding="utf-8"), str(ENTRY_SCRIPT), "exec"), _launcher_globals, _launcher_globals)
'''


def install_resolve_runtime(
    project_root: Path,
    *,
    install_root: Path | None = None,
    launcher_path: Path | None = None,
) -> ResolveInstallationResult:
    resolved_project_root = project_root.resolve()
    runtime_root = (install_root or get_resolve_runtime_directory()).resolve()
    source_root = runtime_root / "src"
    scripts_root = runtime_root / "scripts"
    entry_script_path = scripts_root / "resolve_entry.py"
    target_launcher_path = (launcher_path or (get_resolve_scripts_directory() / f"{APP_NAME}.py")).resolve()

    if runtime_root.exists():
        shutil.rmtree(runtime_root)

    copied_files = 0
    copied_files += _copy_tree(
        source=resolved_project_root / "src",
        destination=source_root,
    )
    copied_files += _copy_file(
        source=resolved_project_root / "scripts" / "resolve_entry.py",
        destination=entry_script_path,
    )

    target_launcher_path.parent.mkdir(parents=True, exist_ok=True)
    target_launcher_path.write_text(render_resolve_launcher(entry_script_path), encoding="utf-8")

    return ResolveInstallationResult(
        install_root=runtime_root,
        entry_script_path=entry_script_path,
        launcher_path=target_launcher_path,
        copied_files=copied_files,
    )


def _copy_tree(source: Path, destination: Path) -> int:
    if not source.exists():
        raise FileNotFoundError(f"Required source directory is missing: {source}")

    copied_files = 0
    for file_path in source.rglob("*"):
        if file_path.is_dir():
            continue
        if any(part == "__pycache__" for part in file_path.parts):
            continue
        if file_path.suffix in {".pyc", ".pyo"}:
            continue
        relative_path = file_path.relative_to(source)
        target_path = destination / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target_path)
        copied_files += 1
    return copied_files


def _copy_file(source: Path, destination: Path) -> int:
    if not source.exists():
        raise FileNotFoundError(f"Required source file is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return 1