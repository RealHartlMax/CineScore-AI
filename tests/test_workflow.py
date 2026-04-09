from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.config import AppConfig
from cinescore_ai.resolve import MockResolveAdapter
from cinescore_ai.workflow import ResolveWorkflowService


class ResolveWorkflowServiceTests(unittest.TestCase):
    def test_queue_preview_render_uses_temp_directory_from_config(self) -> None:
        adapter = MockResolveAdapter()
        service = ResolveWorkflowService(resolve_adapter=adapter)
        config = AppConfig()

        with TemporaryDirectory() as temp_dir:
            config.paths.temp_directory = temp_dir

            job = service.queue_preview_render(config)

            self.assertTrue(Path(temp_dir).exists())
            self.assertEqual(job.target_dir, temp_dir)
            self.assertTrue(job.custom_name.startswith("cinescore-preview_"))

    def test_load_current_timeline_context_returns_adapter_context(self) -> None:
        service = ResolveWorkflowService(resolve_adapter=MockResolveAdapter())

        context = service.load_current_timeline_context()

        self.assertEqual(context.timeline_name, "Assembly Cut")
        self.assertGreater(context.duration_seconds, 0.0)

    def test_render_preview_and_wait_completes_with_output_file(self) -> None:
        adapter = MockResolveAdapter()
        service = ResolveWorkflowService(resolve_adapter=adapter)
        config = AppConfig()

        with TemporaryDirectory() as temp_dir:
            config.paths.temp_directory = temp_dir

            result = service.render_preview_and_wait(
                config,
                poll_interval_seconds=0.0,
                timeout_seconds=1.0,
            )

            self.assertFalse(result.timed_out)
            self.assertEqual(result.final_status.status, "Complete")
            self.assertTrue(result.file_exists)
            self.assertTrue(Path(result.job.target_path).exists())

    def test_queue_preview_render_cleans_up_old_temp_previews(self) -> None:
        adapter = MockResolveAdapter()
        service = ResolveWorkflowService(resolve_adapter=adapter)
        config = AppConfig()

        with TemporaryDirectory() as temp_dir:
            config.paths.temp_directory = temp_dir
            config.paths.temp_preview_retention_days = 7

            old_preview = Path(temp_dir) / "cinescore-preview_old.mp4"
            recent_preview = Path(temp_dir) / "cinescore-preview_recent.mp4"
            old_preview.write_bytes(b"old")
            recent_preview.write_bytes(b"recent")

            now = time()
            ten_days = 10 * 86400
            one_day = 1 * 86400
            os.utime(old_preview, (now - ten_days, now - ten_days))
            os.utime(recent_preview, (now - one_day, now - one_day))

            service.queue_preview_render(config)

            self.assertFalse(old_preview.exists())
            self.assertTrue(recent_preview.exists())
