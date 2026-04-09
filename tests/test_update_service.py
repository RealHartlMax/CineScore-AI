from __future__ import annotations

import unittest
from pathlib import Path

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.update_service import (
    GitHubReleaseUpdateService,
    ReleaseInfo,
    is_newer_version,
    render_windows_update_script,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> object:
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **_kwargs):
        self.calls.append((method, url))
        return self._response


class UpdateServiceTests(unittest.TestCase):
    def test_is_newer_version_compares_numeric_tags(self) -> None:
        self.assertTrue(is_newer_version("v0.2.0", "0.1.9"))
        self.assertFalse(is_newer_version("0.1.0", "0.1.0"))
        self.assertFalse(is_newer_version("0.1.0-beta", "0.1.0"))

    def test_is_newer_version_handles_letter_suffix_prereleases(self) -> None:
        self.assertFalse(is_newer_version("0.1.2b", "0.1.2"))
        self.assertTrue(is_newer_version("0.1.2", "0.1.2b"))
        self.assertTrue(is_newer_version("0.1.2b", "0.1.1"))

    def test_check_for_update_parses_latest_release(self) -> None:
        session = _FakeSession(
            _FakeResponse(
                200,
                [
                    {
                        "tag_name": "v0.2.0",
                        "name": "v0.2.0",
                        "body": "- Added updater\n- Added changelog popup",
                        "html_url": "https://github.com/RealHartlMax/CineScore-AI/releases/tag/v0.2.0",
                        "zipball_url": "https://api.github.com/repos/RealHartlMax/CineScore-AI/zipball/v0.2.0",
                    }
                ],
            )
        )
        service = GitHubReleaseUpdateService(session=session)

        result = service.check_for_update(current_version="0.1.0")

        self.assertTrue(result.update_available)
        self.assertIsNotNone(result.latest_release)
        assert result.latest_release is not None
        self.assertEqual(result.latest_release.version, "0.2.0")
        self.assertEqual([release.version for release in result.newer_releases], ["0.2.0"])
        self.assertEqual(len(session.calls), 1)

    def test_check_for_update_returns_all_newer_releases(self) -> None:
        session = _FakeSession(
            _FakeResponse(
                200,
                [
                    {
                        "tag_name": "v0.1.2b",
                        "name": "v0.1.2b",
                        "body": "hotfix body",
                        "html_url": "https://github.com/RealHartlMax/CineScore-AI/releases/tag/v0.1.2b",
                        "zipball_url": "https://api.github.com/repos/RealHartlMax/CineScore-AI/zipball/v0.1.2b",
                    },
                    {
                        "tag_name": "v0.1.2",
                        "name": "v0.1.2",
                        "body": "stable body",
                        "html_url": "https://github.com/RealHartlMax/CineScore-AI/releases/tag/v0.1.2",
                        "zipball_url": "https://api.github.com/repos/RealHartlMax/CineScore-AI/zipball/v0.1.2",
                    },
                    {
                        "tag_name": "v0.1.1",
                        "name": "v0.1.1",
                        "body": "older body",
                        "html_url": "https://github.com/RealHartlMax/CineScore-AI/releases/tag/v0.1.1",
                        "zipball_url": "https://api.github.com/repos/RealHartlMax/CineScore-AI/zipball/v0.1.1",
                    },
                ],
            )
        )
        service = GitHubReleaseUpdateService(session=session)

        result = service.check_for_update(current_version="0.1.0")

        self.assertTrue(result.update_available)
        self.assertEqual(result.latest_release.version, "0.1.2b")
        self.assertEqual([release.version for release in result.newer_releases], ["0.1.2b", "0.1.2", "0.1.1"])

    def test_check_for_update_treats_404_as_no_release_yet(self) -> None:
        response = _FakeResponse(404, {})
        response.text = '{"message":"Not Found"}'
        session = _FakeSession(response)
        service = GitHubReleaseUpdateService(session=session)

        result = service.check_for_update(current_version="0.1.0")

        self.assertFalse(result.update_available)
        self.assertIsNone(result.latest_release)
        self.assertEqual(result.current_version, "0.1.0")

    def test_render_windows_update_script_includes_runtime_targets(self) -> None:
        script = render_windows_update_script(
            ReleaseInfo(
                version="0.2.0",
                title="v0.2.0",
                body="Release notes",
                html_url="https://example.invalid/release",
                zipball_url="https://example.invalid/release.zip",
            ),
            install_root=Path(r"C:\Users\max\AppData\Roaming\CineScore-AI\resolve-runtime"),
            launcher_path=Path(
                r"C:\Users\max\AppData\Roaming\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\CineScore AI.py"
            ),
        )

        self.assertIn("Stop-Process -Id", script)
        self.assertIn("release.zip", script)
        self.assertIn("resolve_entry.py", script)
        self.assertIn("CineScore AI.py", script)


if __name__ == "__main__":
    unittest.main()