from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.resolve_install import (  # noqa: E402
    get_resolve_scripts_directory,
    install_resolve_runtime,
    render_resolve_launcher,
)


class ResolveInstallTests(unittest.TestCase):
    def test_get_resolve_scripts_directory_windows_path(self) -> None:
        result = get_resolve_scripts_directory(
            platform="win32",
            env={"APPDATA": r"C:\Users\max\AppData\Roaming"},
        )
        self.assertEqual(
            result,
            Path(r"C:\Users\max\AppData\Roaming")
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Support"
            / "Fusion"
            / "Scripts"
            / "Utility",
        )

    def test_render_resolve_launcher_embeds_entry_script_path(self) -> None:
        entry_script_path = Path(r"C:\Installed\CineScore-AI\scripts\resolve_entry.py")
        launcher_script = render_resolve_launcher(entry_script_path)
        self.assertIn(str(entry_script_path), launcher_script)
        self.assertIn("CINESCORE_AI_RESOLVE_ENTRY", launcher_script)
        self.assertIn("exec(compile", launcher_script)

    def test_install_resolve_runtime_copies_minimal_runtime_and_launcher(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "project"
            (project_root / "src" / "cinescore_ai").mkdir(parents=True)
            (project_root / "scripts").mkdir(parents=True)

            (project_root / "src" / "cinescore_ai" / "app.py").write_text("APP = 1\n", encoding="utf-8")
            (project_root / "src" / "cinescore_ai" / "__init__.py").write_text("\n", encoding="utf-8")
            (project_root / "src" / "cinescore_ai" / "__pycache__").mkdir()
            (project_root / "src" / "cinescore_ai" / "__pycache__" / "app.cpython-310.pyc").write_bytes(b"pyc")
            (project_root / "scripts" / "resolve_entry.py").write_text("print('resolve')\n", encoding="utf-8")

            install_root = temp_root / "installed-runtime"
            launcher_path = temp_root / "resolve-scripts" / "CineScore AI.py"
            result = install_resolve_runtime(
                project_root,
                install_root=install_root,
                launcher_path=launcher_path,
            )

            self.assertTrue((install_root / "src" / "cinescore_ai" / "app.py").exists())
            self.assertTrue((install_root / "scripts" / "resolve_entry.py").exists())
            self.assertFalse((install_root / "src" / "cinescore_ai" / "__pycache__").exists())
            self.assertTrue(launcher_path.exists())
            self.assertEqual(result.launcher_path, launcher_path.resolve())
            self.assertGreaterEqual(result.copied_files, 3)
