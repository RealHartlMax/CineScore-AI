from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from cinescore_ai.http_client import build_http_session
from cinescore_ai.paths import APP_NAME
from cinescore_ai.resolve_install import get_resolve_runtime_directory, get_resolve_scripts_directory
from cinescore_ai.version import get_app_version


DEFAULT_GITHUB_OWNER = "RealHartlMax"
DEFAULT_GITHUB_REPO = "CineScore-AI"


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    version: str
    title: str
    body: str
    html_url: str
    zipball_url: str
    published_at: str = ""
    tag_name: str = ""


@dataclass(frozen=True, slots=True)
class UpdateCheckResult:
    current_version: str
    latest_release: ReleaseInfo | None
    update_available: bool


class GitHubReleaseUpdateService:
    def __init__(
        self,
        *,
        owner: str = DEFAULT_GITHUB_OWNER,
        repo: str = DEFAULT_GITHUB_REPO,
        session: Any | None = None,
    ) -> None:
        self._owner = owner.strip() or DEFAULT_GITHUB_OWNER
        self._repo = repo.strip() or DEFAULT_GITHUB_REPO
        self._session = session if session is not None else build_http_session()

    @property
    def latest_release_api_url(self) -> str:
        return f"https://api.github.com/repos/{self._owner}/{self._repo}/releases/latest"

    def check_for_update(self, current_version: str | None = None) -> UpdateCheckResult:
        resolved_current_version = (current_version or get_app_version()).strip() or "0.0.0"
        if self._session is None:
            raise RuntimeError("No HTTP client is available for update checks.")

        try:
            response = self._session.request(
                "GET",
                self.latest_release_api_url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "CineScore-AI-Updater",
                },
                timeout=20,
            )
        except Exception as exc:
            raise RuntimeError(f"Update check failed: {exc}") from exc

        status_code = int(getattr(response, "status_code", 500) or 500)
        if status_code == 404:
            return UpdateCheckResult(
                current_version=resolved_current_version,
                latest_release=None,
                update_available=False,
            )

        if status_code >= 400:
            raise RuntimeError(
                f"Update check failed with HTTP {response.status_code}: {getattr(response, 'text', '')[:240]}"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(f"Update check returned invalid JSON: {exc}") from exc

        latest_release = _parse_release_info(payload)
        return UpdateCheckResult(
            current_version=resolved_current_version,
            latest_release=latest_release,
            update_available=is_newer_version(latest_release.version, resolved_current_version),
        )

    def can_start_self_update(self) -> bool:
        return os.name == "nt"

    def default_install_root(self) -> Path:
        return get_resolve_runtime_directory()

    def default_launcher_path(self) -> Path:
        return get_resolve_scripts_directory() / f"{APP_NAME}.py"

    def start_windows_update(self, release: ReleaseInfo, *, install_root: Path | None = None, launcher_path: Path | None = None) -> Path:
        if not self.can_start_self_update():
            raise RuntimeError("Automatic update is currently only supported on Windows.")

        target_install_root = (install_root or self.default_install_root()).resolve()
        target_launcher_path = (launcher_path or self.default_launcher_path()).resolve()
        script_text = render_windows_update_script(
            release=release,
            install_root=target_install_root,
            launcher_path=target_launcher_path,
        )

        temp_dir = Path(tempfile.gettempdir()) / "cinescore-ai-updater"
        temp_dir.mkdir(parents=True, exist_ok=True)
        script_path = temp_dir / f"update_{_safe_version_token(release.version)}.ps1"
        script_path.write_text(script_text, encoding="utf-8")

        creationflags = 0
        for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= int(getattr(subprocess, flag_name, 0) or 0)

        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            creationflags=creationflags,
            close_fds=True,
        )
        return script_path


def normalize_version(value: str) -> str:
    normalized = value.strip()
    if normalized.lower().startswith("v"):
        normalized = normalized[1:]
    return normalized


def is_newer_version(candidate: str, current: str) -> bool:
    return _version_sort_key(candidate) > _version_sort_key(current)


def render_windows_update_script(release: ReleaseInfo, *, install_root: Path, launcher_path: Path) -> str:
    zip_url = _ps_quote(release.zipball_url)
    release_version = _ps_quote(release.version)
    install_root_value = _ps_quote(str(install_root))
    launcher_path_value = _ps_quote(str(launcher_path))

    return f"""$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms

$zipUrl = {zip_url}
$releaseVersion = {release_version}
$installRoot = {install_root_value}
$launcherPath = {launcher_path_value}

function Show-UpdateError([string]$message) {{
    [System.Windows.Forms.MessageBox]::Show(
        $message,
        'CineScore AI Update',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}}

function Remove-CompiledFiles([string]$root) {{
    if (-not (Test-Path $root)) {{
        return
    }}
    Get-ChildItem -Path $root -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object {{ $_.PSIsContainer -and $_.Name -eq '__pycache__' }} |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $root -Recurse -Force -Include '*.pyc', '*.pyo' -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}}

try {{
    $resolvePath = $null
    $resolveProcess = Get-Process -Name 'Resolve' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($resolveProcess) {{
        try {{
            $resolvePath = $resolveProcess.Path
        }} catch {{
            $resolvePath = $null
        }}
        Stop-Process -Id $resolveProcess.Id -Force
    }}

    $deadline = (Get-Date).AddMinutes(2)
    while (Get-Process -Name 'Resolve' -ErrorAction SilentlyContinue) {{
        if ((Get-Date) -gt $deadline) {{
            throw 'Timed out waiting for DaVinci Resolve to close.'
        }}
        Start-Sleep -Milliseconds 300
    }}

    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('cinescore-ai-release-' + [Guid]::NewGuid().ToString('N'))
    $zipPath = Join-Path $tempRoot 'release.zip'
    $extractRoot = Join-Path $tempRoot 'expanded'
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force

    $sourceRoot = Get-ChildItem -Path $extractRoot -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $sourceRoot) {{
        throw 'Could not locate the extracted CineScore AI release.'
    }}
    if (-not (Test-Path (Join-Path $sourceRoot.FullName 'src\\cinescore_ai\\app.py'))) {{
        $sourceRoot = Get-ChildItem -Path $extractRoot -Recurse -Directory -ErrorAction SilentlyContinue |
            Where-Object {{ Test-Path (Join-Path $_.FullName 'src\\cinescore_ai\\app.py') }} |
            Select-Object -First 1
    }}
    if (-not $sourceRoot) {{
        throw 'The downloaded release does not contain a CineScore AI runtime.'
    }}

    $entryScriptPath = Join-Path $installRoot 'scripts\\resolve_entry.py'
    $installSrcRoot = Join-Path $installRoot 'src'
    $installScriptsRoot = Join-Path $installRoot 'scripts'

    if (Test-Path $installRoot) {{
        Remove-Item -Path $installRoot -Recurse -Force
    }}

    New-Item -ItemType Directory -Path $installSrcRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $installScriptsRoot -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceRoot.FullName 'src\\*') -Destination $installSrcRoot -Recurse -Force
    Copy-Item -Path (Join-Path $sourceRoot.FullName 'scripts\\resolve_entry.py') -Destination $entryScriptPath -Force
    Remove-CompiledFiles -root $installRoot

    $launcherDir = Split-Path -Path $launcherPath -Parent
    if ($launcherDir) {{
        New-Item -ItemType Directory -Path $launcherDir -Force | Out-Null
    }}

    $launcherContent = @"
from __future__ import annotations

import os
from pathlib import Path


ENTRY_SCRIPT = Path(os.environ.get("CINESCORE_AI_RESOLVE_ENTRY", r"$entryScriptPath"))

if not ENTRY_SCRIPT.exists():
    raise RuntimeError(
        "Could not find the installed CineScore AI Resolve entry script at "
        f"'{{ENTRY_SCRIPT}}'. Run the Resolve installer again."
    )

_launcher_globals = globals()
_launcher_globals["__file__"] = str(ENTRY_SCRIPT)
exec(compile(ENTRY_SCRIPT.read_text(encoding="utf-8"), str(ENTRY_SCRIPT), "exec"), _launcher_globals, _launcher_globals)
"@
    Set-Content -Path $launcherPath -Value $launcherContent -Encoding UTF8

    Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue

    if ($resolvePath) {{
        $result = [System.Windows.Forms.MessageBox]::Show(
            "CineScore AI $releaseVersion was installed successfully.`n`nReopen DaVinci Resolve now?",
            'CineScore AI Update',
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Information
        )
        if ($result -eq [System.Windows.Forms.DialogResult]::Yes) {{
            Start-Process -FilePath $resolvePath
        }}
    }} else {{
        [System.Windows.Forms.MessageBox]::Show(
            "CineScore AI $releaseVersion was installed successfully.`n`nPlease reopen DaVinci Resolve manually.",
            'CineScore AI Update',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    }}
}} catch {{
    Show-UpdateError($_.Exception.Message)
}}
"""


def _parse_release_info(payload: Any) -> ReleaseInfo:
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub returned an unexpected release payload.")
    tag_name = str(payload.get("tag_name", "")).strip()
    version = normalize_version(tag_name or str(payload.get("name", "")).strip())
    if not version:
        raise RuntimeError("GitHub did not return a release version.")
    return ReleaseInfo(
        version=version,
        title=str(payload.get("name") or tag_name or f"v{version}").strip(),
        body=str(payload.get("body") or "").strip(),
        html_url=str(payload.get("html_url") or "").strip(),
        zipball_url=str(payload.get("zipball_url") or "").strip(),
        published_at=str(payload.get("published_at") or "").strip(),
        tag_name=tag_name,
    )


def _version_sort_key(value: str) -> tuple[tuple[int, ...], str]:
    normalized = normalize_version(value)
    numeric_portion, _, suffix = normalized.partition("-")
    number_parts = [int(part) for part in re.findall(r"\d+", numeric_portion)]
    while len(number_parts) < 3:
        number_parts.append(0)
    stable_rank = 1 if not suffix else 0
    return tuple(number_parts[:3]), stable_rank, suffix.lower()


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _safe_version_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", normalize_version(value))
    return token or "release"