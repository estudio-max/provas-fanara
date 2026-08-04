"""PySide6 editing desk and its public state-controller API."""
from __future__ import annotations

import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QFile, QIODevice, QThread, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..modelos import BookPlan, PhotoInfo
from ..motor import Config, PlanAnalysisResult, Resultado
from ..projeto import ProjectState, save_project, undo_regeneration
from .cover_dialog import CoverDialog
from .diagnostics import DiagnosticsPanel
from .preview_grid import PreviewGrid
from .sidebar import WorkflowSidebar
from .workers import AnalysisWorker, EditorialWorker, ExportWorker, PreviewWorker


class MainWindow(QMainWindow):
    """Editing desk that orchestrates motor APIs without owning editorial logic."""

    DIAGNOSTICS_BREAKPOINT = 1180

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("Fotolivro · Mesa de edição")
        self.setMinimumSize(840, 540)
        self.resize(1366, 768)

        self.project_state: ProjectState | None = None
        self.folder_path = ""
        self.previews: tuple[object, ...] = ()
        self.is_busy = False
        self.status_message = "Escolha a pasta da sessão para começar."
        self.status_kind = "idle"
        self.last_export_path = ""
        self._draft_config: Config | None = None
        self._cancel_event: threading.Event | None = None
        self._threads: set[QThread] = set()
        self._workers: set[EditorialWorker] = set()
        self._completion: Callable[[object], None] | None = None
        self._closing = False
        self._analysis_failures: tuple[tuple[str, str], ...] = ()

        self._build()
        self._connect()
        self._load_theme()
        self._sync_actions()

    @property
    def mode(self) -> str:
        return self.sidebar.mode

    def _build(self) -> None:
        central = QWidget()
        central.setObjectName("appRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_bar = QFrame()
        self.top_bar.setObjectName("topBar")
        self.top_bar.setFixedHeight(58)
        top = QHBoxLayout(self.top_bar)
        top.setContentsMargins(16, 0, 16, 0)
        top.setSpacing(12)

        mark = QLabel("F")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(mark)
        brand = QVBoxLayout()
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(0)
        name = QLabel("Fotolivro")
        name.setObjectName("brandName")
        self.project_label = QLabel("Novo projeto")
        self.project_label.setObjectName("mutedText")
        brand.addWidget(name)
        brand.addWidget(self.project_label)
        top.addLayout(brand)
        top.addSpacing(12)

        self.status_label = QLabel(self.status_message)
        self.status_label.setObjectName("statusBanner")
        self.status_label.setProperty("kind", self.status_kind)
        self.status_label.setMinimumWidth(120)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top.addWidget(self.status_label, 1)

        self.save_button = QPushButton("Salvar projeto")
        self.save_button.setFixedWidth(116)
        self.save_button.setEnabled(False)
        self.export_button = QPushButton("Exportar PDF")
        self.export_button.setObjectName("primaryButton")
        self.export_button.setFixedWidth(112)
        self.export_button.setEnabled(False)
        top.addWidget(self.save_button)
        top.addWidget(self.export_button)
        root.addWidget(self.top_bar)

        desk = QFrame()
        desk.setObjectName("desk")
        desk_layout = QHBoxLayout(desk)
        desk_layout.setContentsMargins(0, 0, 0, 0)
        desk_layout.setSpacing(0)
        self.sidebar = WorkflowSidebar()
        self.preview_grid = PreviewGrid()
        self.diagnostics = DiagnosticsPanel()
        desk_layout.addWidget(self.sidebar)
        desk_layout.addWidget(self.preview_grid, 1)
        desk_layout.addWidget(self.diagnostics)
        root.addWidget(desk, 1)
        self.setCentralWidget(central)

        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.choose_folder)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_project_dialog)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.export_dialog)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo_regeneration)

    def _connect(self) -> None:
        self.sidebar.folder_requested.connect(self.choose_folder)
        self.sidebar.analysis_requested.connect(self.request_analysis)
        self.sidebar.mode_changed.connect(self._mode_selected)
        self.sidebar.cover_requested.connect(self.open_cover_dialog)
        self.sidebar.cancel_requested.connect(self.cancel_active_operation)
        self.preview_grid.regenerate_requested.connect(self.request_regeneration)
        self.preview_grid.undo_requested.connect(self.undo_regeneration)
        self.save_button.clicked.connect(self.save_project_dialog)
        self.export_button.clicked.connect(self.export_dialog)

    def _load_theme(self) -> None:
        path = Path(__file__).with_name("theme.qss")
        file = QFile(str(path))
        if file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
            self.setStyleSheet(bytes(file.readAll()).decode("utf-8"))
            file.close()

    def choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Escolher pasta de fotografias")
        if path:
            self.select_folder(path)

    def select_folder(self, path: str) -> None:
        """Select a source folder and reset only state derived from the previous one."""
        normalized = os.path.abspath(path)
        self.folder_path = normalized
        title = os.path.basename(normalized.rstrip("\\/")) or normalized
        mode = self.sidebar.mode
        self._draft_config = Config(
            pasta=normalized,
            titulo=title,
            modo=mode,
            marca_dagua=mode == "prova",
            mostrar_codigos=mode == "prova",
            paisagem=True,
            girar_horizontais=False,
        )
        self.project_state = None
        self.previews = ()
        self._analysis_failures = ()
        self.last_export_path = ""
        self.project_label.setText(title)
        self.sidebar.set_folder(normalized)
        self.sidebar.set_project_loaded(False)
        self.preview_grid.show_empty("Analise as fotografias para gerar a primeira diagramação.")
        self.diagnostics.summary_label.setText("Aguardando análise das fotografias.")
        self.set_status("Pasta escolhida. Analise as fotografias para continuar.", "idle")
        self._sync_actions()

    def set_mode(self, mode: str) -> None:
        """Switch rendering mode while preserving page grouping and ordering."""
        self.sidebar.set_mode(mode, emit=False)
        proof = mode == "prova"
        if self._draft_config is not None:
            self._draft_config = replace(
                self._draft_config,
                modo=mode,
                marca_dagua=proof,
                mostrar_codigos=proof,
            )
        if self.project_state is not None:
            config = replace(
                self.project_state.config,
                modo=mode,
                marca_dagua=proof,
                mostrar_codigos=proof,
            )
            plan = replace(self.project_state.plan, mode=mode)
            previous = (
                replace(self.project_state.previous_plan, mode=mode)
                if self.project_state.previous_plan is not None
                else None
            )
            self.project_state = ProjectState(
                config,
                plan,
                self.project_state.photo_paths,
                self.project_state.cache_keys,
                previous,
            )
            self.previews = ()
            self.diagnostics.set_plan(plan, failures=self._analysis_failures)
            self.set_status("Tipo de saída alterado. Atualize a prévia antes de exportar.", "idle")
        self._sync_actions()

    def _mode_selected(self, mode: str) -> None:
        had_preview = bool(self.previews and self.project_state is not None)
        self.set_mode(mode)
        if had_preview and not self.is_busy:
            self.request_preview()

    def begin_operation(self, label: str, cancel_event: threading.Event | None = None) -> None:
        if self.previews:
            self.preview_grid.pending_scroll_position = (
                self.preview_grid.scroll_area.verticalScrollBar().value()
            )
        self.is_busy = True
        self._cancel_event = cancel_event or threading.Event()
        self.sidebar.progress_bar.setValue(0)
        self.sidebar.set_busy(True, label)
        self.preview_grid.show_loading(label)
        self.set_status(label, "loading")
        self._sync_actions()

    def update_operation_progress(self, percent: int, message: str) -> None:
        self.sidebar.progress_bar.setValue(max(0, min(100, int(percent))))
        self.sidebar.progress_label.setText(message)
        self.set_status(message, "loading")

    def cancel_active_operation(self) -> None:
        if self._cancel_event is None:
            return
        self._cancel_event.set()
        for worker in tuple(self._workers):
            worker.cancel()
        self.sidebar.cancel_button.setEnabled(False)
        self.set_status("Cancelamento solicitado. Finalizando a etapa atual…", "loading")

    def _end_operation(self) -> None:
        self.is_busy = False
        self._cancel_event = None
        self.sidebar.set_busy(False)
        self._sync_actions()

    def request_analysis(self) -> None:
        if self._draft_config is None or self.is_busy:
            return
        event = threading.Event()
        self.begin_operation("Analisando fotografias…", event)
        self._start_worker(
            AnalysisWorker(self._draft_config, event),
            self._analysis_completed,
        )

    def _analysis_completed(self, result: object) -> None:
        if isinstance(result, PlanAnalysisResult):
            self.apply_analysis_result(
                result.plan,
                photos=result.photos,
                failures=result.failures,
            )
        elif isinstance(result, BookPlan):
            self.apply_analysis_result(result)
        else:
            raise TypeError("O motor não retornou um plano editorial.")
        self.request_preview()

    def apply_analysis_result(
        self,
        plan: BookPlan,
        *,
        photos: tuple[PhotoInfo, ...] = (),
        failures: tuple[tuple[str, str], ...] = (),
    ) -> None:
        """Install a motor-produced plan; preview remains a separate state."""
        if self._draft_config is None:
            self._draft_config = Config(
                self.folder_path or os.getcwd(),
                modo=plan.mode,
                semente=plan.seed,
                paisagem=True,
                girar_horizontais=False,
            )
        config = replace(self._draft_config, modo=plan.mode, semente=plan.seed)
        paths = (
            tuple(photo.path for photo in photos)
            if photos
            else tuple(dict.fromkeys(photo_id for page in plan.pages for photo_id in page.photo_ids))
        )
        self.project_state = ProjectState(config, plan, paths)
        self._analysis_failures = tuple(failures)
        self.sidebar.set_project_loaded(True)
        self.previews = ()
        self._end_operation()
        self.diagnostics.set_plan(plan, failures=self._analysis_failures)
        self.set_status("Análise concluída. Preparando a prévia editorial.", "success")
        self._sync_actions()

    def request_preview(self) -> None:
        if self.project_state is None or self.is_busy:
            return
        event = threading.Event()
        self.begin_operation("Preparando a prévia…", event)
        worker = PreviewWorker(
            self.project_state.config.to_motor_config(),
            self.project_state.plan,
            self._preview_width(),
            event,
        )
        self._start_worker(worker, self.apply_preview_ready)

    def _preview_width(self) -> int:
        return max(320, min(520, round(self.preview_grid.width() * 0.44)))

    def apply_preview_ready(self, previews: object) -> None:
        if self.project_state is None:
            raise ValueError("Não há projeto para receber a prévia.")
        items = tuple(previews)  # type: ignore[arg-type]
        self.previews = items
        self.preview_grid.set_previews(self.project_state.plan, items)
        self._end_operation()
        self.set_status("Prévia pronta para revisão.", "success")
        self._sync_actions()

    def request_regeneration(self) -> None:
        if self.project_state is None or self.is_busy:
            return
        config = replace(
            self.project_state.config,
            semente=self.project_state.plan.seed + 1,
        ).to_motor_config()
        event = threading.Event()
        self.begin_operation("Gerando outra diagramação…", event)
        self._start_worker(AnalysisWorker(config, event), self._regeneration_completed)

    def _regeneration_completed(self, result: object) -> None:
        if isinstance(result, PlanAnalysisResult):
            self._analysis_failures = result.failures
            result = result.plan
        if not isinstance(result, BookPlan):
            raise TypeError("O motor não retornou uma nova diagramação.")
        self.apply_regenerated_plan(result)
        self.request_preview()

    def apply_regenerated_plan(self, plan: BookPlan) -> None:
        if self.project_state is None:
            raise ValueError("Não há diagramação anterior para substituir.")
        manual_cover = self.project_state.config.cover_ids
        if manual_cover:
            plan = replace(plan, cover_photo_ids=manual_cover)
        config = replace(self.project_state.config, semente=plan.seed)
        self.project_state = ProjectState(
            config,
            plan,
            self.project_state.photo_paths,
            self.project_state.cache_keys,
            self.project_state.plan,
        )
        current_scroll = self.preview_grid.scroll_area.verticalScrollBar().value()
        if current_scroll > 0 or self.preview_grid.pending_scroll_position == 0:
            self.preview_grid.pending_scroll_position = current_scroll
        self.previews = ()
        self._end_operation()
        self.diagnostics.set_plan(plan, failures=self._analysis_failures)
        self.set_status("Nova diagramação criada. A anterior pode ser desfeita.", "success")
        self._sync_actions()

    def undo_regeneration(self) -> None:
        if self.project_state is None or self.project_state.previous_plan is None or self.is_busy:
            return
        scroll = self.preview_grid.scroll_area.verticalScrollBar().value()
        self.project_state = undo_regeneration(self.project_state)
        self.preview_grid.pending_scroll_position = scroll
        self.previews = ()
        self.diagnostics.set_plan(
            self.project_state.plan,
            failures=self._analysis_failures,
        )
        self.set_status("Diagramação anterior restaurada. Atualizando a prévia…", "success")
        self._sync_actions()
        if self.isVisible():
            self.request_preview()

    def open_cover_dialog(self) -> None:
        if self.project_state is None:
            return
        selected = self.project_state.plan.cover_photo_ids
        all_ids = tuple(
            dict.fromkeys(photo_id for page in self.project_state.plan.pages for photo_id in page.photo_ids)
        )
        remaining = tuple(photo_id for photo_id in all_ids if photo_id not in selected)
        dialog = CoverDialog(selected, remaining, self)
        dialog.replacement_requested.connect(self._cover_replaced)
        dialog.open()

    def _cover_replaced(self, slot: int, photo_id: str) -> None:
        self.replace_cover_photo(slot, photo_id)
        self.request_preview()

    def replace_cover_photo(self, slot: int, photo_id: str) -> None:
        if self.project_state is None:
            raise ValueError("Analise as fotografias antes de alterar a capa.")
        covers = list(self.project_state.plan.cover_photo_ids)
        if not 0 <= slot < len(covers):
            raise IndexError("Posição de capa inválida.")
        available = {
            photo for page in self.project_state.plan.pages for photo in page.photo_ids
        }
        if photo_id not in available:
            raise ValueError("A fotografia escolhida não pertence a este projeto.")
        if photo_id in covers and covers[slot] != photo_id:
            raise ValueError("Essa fotografia já está na capa.")
        covers[slot] = photo_id
        selected = tuple(covers)
        config = replace(self.project_state.config, cover_ids=selected)
        plan = replace(self.project_state.plan, cover_photo_ids=selected)
        self.project_state = ProjectState(
            config,
            plan,
            self.project_state.photo_paths,
            self.project_state.cache_keys,
            self.project_state.previous_plan,
        )
        self.previews = ()
        self.set_status("Foto da capa substituída. A posição foi preservada.", "success")
        self._sync_actions()

    def export_dialog(self) -> None:
        if self.project_state is None or not self.previews or self.is_busy:
            return
        default = self.project_state.config.to_motor_config().com_padroes().saida
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Exportar PDF",
            default,
            "Documento PDF (*.pdf)",
        )
        if path:
            self.request_export(path)

    def request_export(self, path: str) -> None:
        if self.project_state is None or self.is_busy:
            return
        config = replace(self.project_state.config, saida=path)
        self.project_state = ProjectState(
            config,
            self.project_state.plan,
            self.project_state.photo_paths,
            self.project_state.cache_keys,
            self.project_state.previous_plan,
        )
        event = threading.Event()
        self.begin_operation("Exportando PDF…", event)
        self._start_worker(
            ExportWorker(config.to_motor_config(), self.project_state.plan, event),
            self.apply_export_success,
        )

    def apply_export_success(self, result: Resultado | object) -> None:
        path = str(getattr(result, "saida", ""))
        self.last_export_path = path
        self._end_operation()
        self.set_status(
            f"PDF exportado com sucesso: {os.path.basename(path) or path}",
            "success",
        )
        self._sync_actions()

    def save_project_dialog(self) -> None:
        if self.project_state is None or self.is_busy:
            return
        default = os.path.join(self.folder_path, "fotolivro.provas.json")
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Salvar projeto",
            default,
            "Projeto Fotolivro (*.provas.json);;JSON (*.json)",
        )
        if path:
            try:
                save_project(path, self.project_state)
            except OSError as exc:
                self.apply_failure(str(exc))
            else:
                self.set_status("Projeto salvo. As fotografias permanecem na pasta original.", "success")

    def apply_failure(self, message: str) -> None:
        detail = message.strip().rstrip(".") or "ocorreu um erro inesperado"
        self._end_operation()
        self.set_status(
            f"Não foi possível concluir: {detail}. Verifique a pasta e tente novamente.",
            "error",
        )
        if self.project_state is None:
            self.preview_grid.show_empty(
                "A análise não terminou. Confira a pasta e use Analisar fotografias novamente."
            )

    def apply_cancelled(self) -> None:
        self._end_operation()
        self.set_status("Operação cancelada. Você pode tentar novamente.", "idle")
        if self.project_state is None:
            self.preview_grid.show_empty("Escolha ou analise uma pasta quando quiser continuar.")

    def set_status(self, message: str, kind: str = "idle") -> None:
        self.status_message = message
        self.status_kind = kind
        self._refresh_status_text()
        self.status_label.setProperty("kind", kind)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _refresh_status_text(self) -> None:
        available = max(80, self.status_label.width() - 24)
        visible = self.status_label.fontMetrics().elidedText(
            self.status_message,
            Qt.TextElideMode.ElideRight,
            available,
        )
        self.status_label.setText(visible)
        self.status_label.setToolTip(self.status_message if visible != self.status_message else "")

    def _sync_actions(self) -> None:
        has_folder = bool(self.folder_path)
        has_plan = self.project_state is not None
        preview_ready = has_plan and bool(self.previews)
        self.sidebar.analyze_button.setEnabled(has_folder and not self.is_busy)
        self.sidebar.set_cover_ready(bool(preview_ready))
        self.preview_grid.regenerate_button.setEnabled(bool(preview_ready and not self.is_busy))
        self.preview_grid.undo_button.setEnabled(
            bool(has_plan and self.project_state.previous_plan is not None and not self.is_busy)
        )
        self.save_button.setEnabled(bool(has_plan and not self.is_busy))
        self.export_button.setEnabled(bool(preview_ready and not self.is_busy))

    def _start_worker(
        self,
        worker: EditorialWorker,
        completed: Callable[[object], None],
    ) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        self._threads.add(thread)
        self._workers.add(worker)
        self._completion = completed
        thread.started.connect(worker.run)
        worker.progress.connect(self.update_operation_progress)
        worker.completed.connect(self._worker_completed)
        worker.failed.connect(self._worker_failed)
        worker.cancelled.connect(self._worker_cancelled)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._forget_thread(thread, worker))
        thread.start()

    def _worker_completed(self, result: object) -> None:
        callback, self._completion = self._completion, None
        try:
            if callback is not None:
                callback(result)
        except Exception as exc:
            self.apply_failure(str(exc))

    def _worker_failed(self, message: str) -> None:
        self._completion = None
        self.apply_failure(message)

    def _worker_cancelled(self) -> None:
        self._completion = None
        self.apply_cancelled()

    def _forget_thread(self, thread: QThread, worker: EditorialWorker) -> None:
        self._threads.discard(thread)
        self._workers.discard(worker)
        if self._closing and not self._threads:
            QTimer.singleShot(0, self, self.close)

    def request_shutdown(self) -> None:
        """Request cooperative cancellation while leaving Qt's event loop responsive."""
        self._closing = True
        if self._cancel_event is not None:
            self._cancel_event.set()
        for worker in tuple(self._workers):
            worker.cancel()
        for thread in tuple(self._threads):
            thread.requestInterruption()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.request_shutdown()
        if self._threads:
            event.ignore()
            self.setEnabled(False)
            self.set_status("Fechando após cancelar a operação em andamento…", "loading")
            QTimer.singleShot(5000, self, self._warn_shutdown_delay)
            return
        event.accept()

    def _warn_shutdown_delay(self) -> None:
        if self._closing and self._threads:
            self.set_status(
                "A operação ainda está finalizando com segurança. A janela continua responsiva.",
                "loading",
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.diagnostics.setVisible(self.width() >= self.DIAGNOSTICS_BREAKPOINT)
        self._refresh_status_text()
