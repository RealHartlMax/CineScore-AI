from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_src_path() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    return project_root


PROJECT_ROOT = _bootstrap_src_path()

from cinescore_ai.resolve_install import (  # noqa: E402
    get_resolve_runtime_directory,
    get_resolve_scripts_directory,
    install_resolve_runtime,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Install CineScore AI for DaVinci Resolve with a single visible launcher file in the Resolve Scripts menu."
        )
    )
    parser.add_argument(
        "--install-root",
        type=Path,
        default=get_resolve_runtime_directory(),
        help="Directory that will contain the installed runtime outside the Resolve scripts folder.",
    )
    parser.add_argument(
        "--launcher-path",
        type=Path,
        default=get_resolve_scripts_directory() / "CineScore AI.py",
        help="Path of the single launcher file that Resolve will display in its Scripts menu.",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    result = install_resolve_runtime(
        PROJECT_ROOT,
        install_root=args.install_root,
        launcher_path=args.launcher_path,
    )

    print(f"Installed runtime: {result.install_root}")
    print(f"Installed entry script: {result.entry_script_path}")
    print(f"Installed Resolve launcher: {result.launcher_path}")
    print(f"Copied files: {result.copied_files}")
    print("Resolve will only show the launcher file in its Scripts menu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())