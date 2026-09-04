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
        self._terminal_lock = threading.RLock()
        self._terminal_state = "active"
        self._started = False

    def cancel(self) -> bool:
        with self._terminal_lock:
            if self._terminal_state != "active":
                return False
            self.cancel_event.set()
            self._terminal_state = "cancelled"
            return True

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

    def _error_message(self, exc: Exception) -> str:
        return str(exc) or exc.__class__.__name__

    def _claim_cancellation_if_requested(self) -> bool:
        with self._terminal_lock:
            if self._terminal_state == "active" and self._is_cancelled():
                self._terminal_state = "cancelled"
            return self._terminal_state == "cancelled"

    def _claim_terminal(self, terminal_state: str) -> str:
        with self._terminal_lock:
            if self._terminal_state == "active":
                if self._is_cancelled():
                    self._terminal_state = "cancelled"
                elif self._terminal_state == "active":
                    self._terminal_state = terminal_state
            return self._terminal_state

    def _claim_cancelled(self) -> str:
        with self._terminal_lock:
            if self._terminal_state == "active":
                self._terminal_state = "cancelled"
            return self._terminal_state

    def _emit_terminal(self, terminal_state: str, payload: object | None = None) -> None:
        if terminal_state == "cancelled":
            self.cancelled.emit()
        elif terminal_state == "completed":
            self.completed.emit(payload)
        elif terminal_state == "failed":
            assert isinstance(payload, Exception)
            self.failed.emit(self._error_message(payload))

    @Slot()
    def run(self) -> None:
        with self._run_lock:
            if self._started:
                return
            self._started = True
        if self._claim_cancellation_if_requested():
            self._emit_terminal("cancelled")
            return
        try:
            result = self._execute()
        except motor.Cancelado:
            self._emit_terminal(self._claim_cancelled())
        except Exception as exc:  # the controller turns details into an actionable banner
            self._emit_terminal(self._claim_terminal("failed"), exc)
        else:
            self._emit_terminal(self._claim_terminal("completed"), result)


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


class PageCycleWorker(EditorialWorker):
    """Cycle and render exactly one internal page on the worker thread."""

    def __init__(
        self,
        config: Config,
        plan: BookPlan,
        page_number: int,
        preview_width: int,
        cancel_event: threading.Event | None = None,
        *,
        operation: Callable[..., object] = motor.ciclar_preview_pagina,
    ) -> None:
        super().__init__(cancel_event)
        self.config = config
        self.plan = plan
        self.page_number = page_number
        self.preview_width = preview_width
        self.operation = operation

    def _execute(self) -> object:
        return self.operation(
            self.config,
            self.plan,
            self.page_number,
            self.preview_width,
            cancelar=self.cancel_event,
        )

    def _error_message(self, exc: Exception) -> str:
        detail = str(exc) or exc.__class__.__name__
        if detail == "Thumbnail width must be positive":
            detail = "a largura da prévia deve ser maior que zero."
        elif detail.startswith("Unknown template:"):
            detail = "o layout desta página não é reconhecido."
        elif detail.startswith("Unknown page number:"):
            detail = "a página solicitada não existe no plano."
        elif detail.startswith("Missing preview assets:"):
            detail = "faltam fotos necessárias para renderizar esta página."
        return f"Não foi possível atualizar a página: {detail}"


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
