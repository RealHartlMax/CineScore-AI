from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
import re

from cinescore_ai.config import AppConfig
from cinescore_ai.resolve import PreviewRenderJob, PreviewRenderRequest, RenderJobStatus, ResolveAdapter, ResolveTimelineContext


@dataclass(slots=True)
class PreviewRenderProgressUpdate:
    phase: str
    message: str
    job_id: str | None = None
    status: str | None = None
    completion_percentage: float | None = None
    target_path: str | None = None


@dataclass(slots=True)
class PreviewRenderExecutionResult:
    context: ResolveTimelineContext
    job: PreviewRenderJob
    final_status: RenderJobStatus
    file_exists: bool
    timed_out: bool


class ResolveWorkflowService:
    def __init__(self, resolve_adapter: ResolveAdapter) -> None:
        self._resolve_adapter = resolve_adapter

    def load_current_timeline_context(self) -> ResolveTimelineContext:
        return self._resolve_adapter.get_current_timeline_context()

    def queue_preview_render(self, config: AppConfig) -> PreviewRenderJob:
        context = self._resolve_adapter.get_current_timeline_context()
        target_dir = Path(config.paths.temp_directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_old_previews(target_dir, config.paths.temp_preview_retention_days)

        request = PreviewRenderRequest(
            target_dir=str(target_dir),
            custom_name=self._build_preview_name(context),
            frame_rate=context.frame_rate,
        )
        return self._resolve_adapter.queue_preview_render(request)

    def get_render_job_status(self, job_id: str):
        return self._resolve_adapter.get_render_job_status(job_id)

    def resolve_preview_path(self, config: AppConfig, preferred_path: str | None = None) -> Path:
        if preferred_path:
            preferred = Path(preferred_path)
            if preferred.exists():
                return preferred

        temp_dir = Path(config.paths.temp_directory)
        candidates = sorted(
            temp_dir.glob("cinescore-preview_*.mp4"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]
        raise FileNotFoundError(f"No preview render was found in {temp_dir}.")

    def render_preview_and_wait(
        self,
        config: AppConfig,
        progress_callback=None,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float = 600.0,
    ) -> PreviewRenderExecutionResult:
        context = self._resolve_adapter.get_current_timeline_context()
        target_dir = Path(config.paths.temp_directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        deleted_count = self._cleanup_old_previews(target_dir, config.paths.temp_preview_retention_days)
        if deleted_count > 0:
            self._emit_progress(
                progress_callback,
                PreviewRenderProgressUpdate(
                    phase="cleanup",
                    message=(
                        f"Cleaned up {deleted_count} old preview file(s) older than "
                        f"{config.paths.temp_preview_retention_days} day(s)."
                    ),
                ),
            )

        request = PreviewRenderRequest(
            target_dir=str(target_dir),
            custom_name=self._build_preview_name(context),
            frame_rate=context.frame_rate,
        )

        job = self._resolve_adapter.queue_preview_render(request)
        self._emit_progress(
            progress_callback,
            PreviewRenderProgressUpdate(
                phase="queued",
                message=f"Queued preview render job '{job.job_id}'.",
                job_id=job.job_id,
                status=job.status,
                completion_percentage=0.0,
                target_path=job.target_path,
            ),
        )

        initial_status = self._resolve_adapter.start_render_job(job.job_id)
        self._emit_progress(
            progress_callback,
            PreviewRenderProgressUpdate(
                phase="started",
                message=f"Started preview render job '{job.job_id}'.",
                job_id=job.job_id,
                status=initial_status.status,
                completion_percentage=initial_status.completion_percentage,
                target_path=job.target_path,
            ),
        )

        deadline = monotonic() + timeout_seconds
        final_status = initial_status
        timed_out = False
        while True:
            final_status = self._resolve_adapter.get_render_job_status(job.job_id)
            self._emit_progress(
                progress_callback,
                PreviewRenderProgressUpdate(
                    phase="polling",
                    message=self._build_poll_message(job.job_id, final_status),
                    job_id=job.job_id,
                    status=final_status.status,
                    completion_percentage=final_status.completion_percentage,
                    target_path=job.target_path,
                ),
            )
            if _is_terminal_render_status(final_status.status):
                break
            if monotonic() >= deadline:
                timed_out = True
                break
            sleep(max(poll_interval_seconds, 0.0))

        file_exists = Path(job.target_path).exists()
        if timed_out:
            self._emit_progress(
                progress_callback,
                PreviewRenderProgressUpdate(
                    phase="timeout",
                    message=f"Timed out while waiting for render job '{job.job_id}'.",
                    job_id=job.job_id,
                    status=final_status.status,
                    completion_percentage=final_status.completion_percentage,
                    target_path=job.target_path,
                ),
            )
        else:
            self._emit_progress(
                progress_callback,
                PreviewRenderProgressUpdate(
                    phase="completed",
                    message=self._build_completion_message(job.job_id, final_status, file_exists),
                    job_id=job.job_id,
                    status=final_status.status,
                    completion_percentage=final_status.completion_percentage,
                    target_path=job.target_path,
                ),
            )

        return PreviewRenderExecutionResult(
            context=context,
            job=job,
            final_status=final_status,
            file_exists=file_exists,
            timed_out=timed_out,
        )

    def _build_preview_name(self, context: ResolveTimelineContext) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_fragment = _slugify_fragment(context.project_name)
        timeline_fragment = _slugify_fragment(context.timeline_name)
        return f"cinescore-preview_{project_fragment}_{timeline_fragment}_{timestamp}"

    def _emit_progress(self, progress_callback, update: PreviewRenderProgressUpdate) -> None:
        if callable(progress_callback):
            progress_callback(update)

    def _build_poll_message(self, job_id: str, status: RenderJobStatus) -> str:
        if status.completion_percentage is None:
            return f"Render job '{job_id}' status: {status.status}."
        return f"Render job '{job_id}' status: {status.status} ({status.completion_percentage:.0f}%)."

    def _build_completion_message(self, job_id: str, status: RenderJobStatus, file_exists: bool) -> str:
        suffix = " Output file is present." if file_exists else " Output file is not visible yet."
        if status.completion_percentage is None:
            return f"Render job '{job_id}' finished with status '{status.status}'.{suffix}"
        return (
            f"Render job '{job_id}' finished with status '{status.status}' "
            f"at {status.completion_percentage:.0f}%.{suffix}"
        )

    def _cleanup_old_previews(self, temp_dir: Path, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff_timestamp = datetime.now().timestamp() - (retention_days * 86400)
        deleted_count = 0
        for candidate in temp_dir.glob("cinescore-preview_*.mp4"):
            try:
                if candidate.stat().st_mtime >= cutoff_timestamp:
                    continue
                candidate.unlink()
                deleted_count += 1
            except OSError:
                continue
        return deleted_count


def _slugify_fragment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return cleaned or "untitled"


def _is_terminal_render_status(status: str) -> bool:
    normalized = status.strip().lower()
    return normalized in {"complete", "completed", "failed", "error", "cancelled", "canceled", "stopped"}
