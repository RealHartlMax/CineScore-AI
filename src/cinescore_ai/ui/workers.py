from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(object)
    finished = Signal()


class BackgroundTask(QRunnable):
    def __init__(self, callback: Callable[..., Any], with_progress: bool = False) -> None:
        super().__init__()
        self.callback = callback
        self.with_progress = with_progress
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            if self.with_progress:
                result = self.callback(self.signals.progress.emit)
            else:
                result = self.callback()
        except Exception as exc:  # pragma: no cover - Qt worker exceptions are integration-level
            self.signals.failed.emit(str(exc))
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
