"""Cancelable Qt workers that adapt the editorial motor to uniform signals."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from .. import motor
from ..modelos import BookPlan
from ..motor import Config


class EditorialWorker(QObject):
    """Base worker with the signal contract used by the editing desk."""

    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, cancel_event: threading.Event | None = None) -> None:
        super().__init__()
        self.cancel_event = cancel_event or threading.Event()
        self._run_lock = threading.Lock()
        self._started = False

    def cancel(self) -> None:
        self.cancel_event.set()

    def _is_cancelled(self) -> bool:
        thread = QThread.currentThread()
        return self.cancel_event.is_set() or thread.isInterruptionRequested()

    def _progress(self, done: int, total: int, message: str) -> None:
        if self._is_cancelled():
            raise motor.Cancelado()
        percent = round(max(0, done) * 100 / max(1, total))
        self.progress.emit(max(0, min(100, percent)), str(message))

    def _execute(self) -> Any:
        raise NotImplementedError

    @Slot()
    def run(self) -> None:
        with self._run_lock:
            if self._started:
                return
            self._started = True
        if self._is_cancelled():
            self.cancelled.emit()
            return
        try:
            result = self._execute()
        except motor.Cancelado:
            self.cancelled.emit()
        except Exception as exc:  # the controller turns details into an actionable banner
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            if self._is_cancelled():
                self.cancelled.emit()
            else:
                self.completed.emit(result)


class AnalysisWorker(EditorialWorker):
    """Analyze a folder and compose its first or regenerated ``BookPlan``."""

    def __init__(
        self,
        config: Config,
        cancel_event: threading.Event | None = None,
        *,
        operation: Callable[..., object] = motor.analisar_plano,
    ) -> None:
        super().__init__(cancel_event)
        self.config = config
        self.operation = operation

    def _execute(self) -> object:
        return self.operation(self.config, progresso=self._progress, cancelar=self.cancel_event)


class PreviewWorker(EditorialWorker):
    """Render thumbnails from the exact same plan later supplied to export."""

    def __init__(
        self,
        config: Config,
        plan: BookPlan,
        width: int = 420,
        cancel_event: threading.Event | None = None,
        *,
        operation: Callable[..., object] = motor.gerar_preview,
    ) -> None:
        super().__init__(cancel_event)
        self.config = config
        self.plan = plan
        self.width = width
        self.operation = operation

    def _execute(self) -> object:
        return self.operation(
            self.config,
            self.plan,
            self.width,
            progresso=self._progress,
            cancelar=self.cancel_event,
        )


class ExportWorker(EditorialWorker):
    """Publish a PDF atomically through the motor."""

    def __init__(
        self,
        config: Config,
        plan: BookPlan,
        cancel_event: threading.Event | None = None,
        *,
        operation: Callable[..., object] = motor.exportar,
    ) -> None:
        super().__init__(cancel_event)
        self.config = config
        self.plan = plan
        self.operation = operation

    def _execute(self) -> object:
        return self.operation(
            self.config,
            self.plan,
            progresso=self._progress,
            cancelar=self.cancel_event,
        )
