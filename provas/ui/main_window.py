"""PySide6 editing desk and its public state-controller API."""
from __future__ import annotations

import os
import threading
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import Callable

from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import QFile, QIODevice, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QPixmap, QShortcut
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

from ..capas import fotos_usadas_pela_capa, validate_cover_style
from ..capa_classica import ClassicCrop
from ..ciclo_paginas import tem_alternativa
from ..modelos import BookPlan, PhotoInfo
from ..motor import (
    Config,
    PageCycleResult,
    PlanAnalysisResult,
    Resultado,
    render_style_fingerprint,
)
from ..projeto import ProjectSchemaError, ProjectState, load_project, save_project, undo_regeneration
from .. import recursos
from .cover_dialog import CoverDialog
from .crop_dialog import CropDialog
from .diagnostics import DiagnosticsPanel
from .preview_grid import PreviewGrid
from .sidebar import WorkflowSidebar
from .workers import AnalysisWorker, EditorialWorker, ExportWorker, PageCycleWorker, PreviewWorker


class MainWindow(QMainWindow):
    """Editing desk that orchestrates motor APIs without owning editorial logic."""

    #: Emitido a cada mudança de estado do projeto — pasta, plano, prévia, ocupado.
    #: O passo a passo escuta isto para saber quando uma etapa terminou.
    estado_mudou = Signal()

    DIAGNOSTICS_BREAKPOINT = 1180

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle(f"{recursos.PRODUCT_NAME} · Mesa de edição")
        self.setWindowIcon(QIcon(str(recursos.caminho("icone.ico"))))
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
        self._cover_dialog: CoverDialog | None = None
        self._crop_dialog: CropDialog | None = None
        self._classic_preview_photo_id = ""
        self._classic_preview_target: tuple[int, int] | None = None
        self._page_cycle_queue: deque[int] = deque()
        self._page_cycle_worker: PageCycleWorker | None = None
        self._page_cycle_thread: QThread | None = None
        self._page_cycle_busy: set[int] = set()
        self._page_cycle_aspect_ratios: dict[str, float] = {}
        self._deferred_cover_identity: dict[str, str] | None = None
        self._deferred_page_appearance: tuple[str, bool] | None = None

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

        mark = QLabel()
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet("background: transparent;")
        mark.setPixmap(QPixmap(str(recursos.caminho("fanara-symbol.png"))).scaled(
            32, 32, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        top.addWidget(mark)
        brand = QVBoxLayout()
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(0)
        name = QLabel(recursos.PRODUCT_NAME)
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

        self.open_project_button = QPushButton("Abrir projeto")
        self.open_project_button.setAccessibleName(f"Abrir projeto {recursos.PRODUCT_NAME}")
        self.open_project_button.setToolTip("Abrir um projeto salvo (Ctrl+O)")
        self.open_project_button.setFixedWidth(112)
        self.save_button = QPushButton("Salvar projeto")
        self.save_button.setFixedWidth(116)
        self.save_button.setEnabled(False)
        self.export_button = QPushButton("Exportar PDF")
        self.export_button.setObjectName("primaryButton")
        self.export_button.setFixedWidth(112)
        self.export_button.setEnabled(False)
        top.addWidget(self.open_project_button)
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

        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_project_dialog)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, activated=self.choose_folder)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_project_dialog)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.export_dialog)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo_regeneration)

    def _connect(self) -> None:
        self.sidebar.folder_requested.connect(self.choose_folder)
        self.sidebar.analysis_requested.connect(self.request_analysis)
        self.sidebar.mode_changed.connect(self._mode_selected)
        self.sidebar.cover_style_changed.connect(self.set_cover_style)
        self.sidebar.cover_identity_changed.connect(self.set_cover_identity)
        self.sidebar.page_appearance_changed.connect(self.set_page_appearance)
        self.sidebar.cover_requested.connect(self.open_cover_dialog)
        self.sidebar.crop_requested.connect(self.open_crop_dialog)
        self.sidebar.cancel_requested.connect(self.cancel_active_operation)
        self.preview_grid.regenerate_requested.connect(self.request_regeneration)
        self.preview_grid.undo_requested.connect(self.undo_regeneration)
        self.preview_grid.page_layout_requested.connect(self.request_page_cycle)
        self.open_project_button.clicked.connect(self.open_project_dialog)
        self.save_button.clicked.connect(self.save_project_dialog)
        self.export_button.clicked.connect(self.export_dialog)

    def _load_theme(self) -> None:
        path = Path(__file__).with_name("theme.qss")
        file = QFile(str(path))
        if file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
            self.setStyleSheet(bytes(file.readAll()).decode("utf-8"))
            file.close()

    def choose_folder(self) -> None:
        if self.is_busy:
            return
        path = QFileDialog.getExistingDirectory(self, "Escolher pasta de fotografias")
        if path:
            self.select_folder(path)

    def open_project_dialog(self) -> None:
        """Choose and restore a project without composing a replacement plan."""
        if self.is_busy:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Abrir projeto",
            self.folder_path,
            f"Projeto {recursos.PRODUCT_NAME} (*.provas.json);;JSON (*.json)",
        )
        if path:
            self.open_project(path)

    def open_project(self, path: str) -> None:
        """Restore persisted UI and plan state, then render that exact plan."""
        if self.is_busy:
            return
        try:
            state = load_project(path)
        except (OSError, ProjectSchemaError, ValueError) as exc:
            self.apply_failure(str(exc))
            return

        self.project_state = state
        self._draft_config = state.config.to_motor_config()
        self.folder_path = os.path.abspath(state.config.pasta)
        self.previews = ()
        self._page_cycle_aspect_ratios = {}
        self.last_export_path = ""
        missing = state.missing_paths
        self._analysis_failures = tuple(
            (os.path.basename(source) or source, "arquivo de origem ausente")
            for source in missing
        )

        self.project_label.setText(Path(path).name.removesuffix(".provas.json"))
        self.sidebar.set_folder(self.folder_path)
        self.sidebar.set_project_loaded(True)
        self.sidebar.set_mode(state.config.modo, emit=False)
        self.sidebar.set_cover_style(state.config.estilo_capa, emit=False)
        self.sidebar.set_cover_identity(state.config)
        self.sidebar.set_page_appearance(
            state.config.fundo_paginas, state.config.sombra_fotos, emit=False
        )
        self.sidebar.set_page_appearance_ready(True)
        self.preview_grid.show_empty("Carregando a prévia do projeto salvo…")
        self.diagnostics.set_plan(
            state.plan,
            failed_count=len(missing),
            failures=self._analysis_failures,
        )
        if missing:
            self.set_status(
                "Projeto aberto, mas há fotografias de origem ausentes.", "warning"
            )
        else:
            self.set_status("Projeto aberto. Preparando a prévia salva.", "success")
        self._sync_actions()
        self.request_preview()

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
        self.sidebar.set_cover_style(self._draft_config.estilo_capa, emit=False)
        self.sidebar.set_cover_identity(self._draft_config)
        self.sidebar.set_page_appearance(
            self._draft_config.fundo_paginas,
            self._draft_config.sombra_fotos,
            emit=False,
        )
        self.sidebar.set_page_appearance_ready(False)
        self.project_state = None
        self.previews = ()
        self._page_cycle_aspect_ratios = {}
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

    def set_cover_style(self, style: str) -> None:
        """Change only the cover renderer; the editorial plan remains immutable."""
        normalized = validate_cover_style(style)
        self.sidebar.set_cover_style(normalized, emit=False)
        if self._draft_config is not None:
            self._draft_config = replace(self._draft_config, estilo_capa=normalized)
        if self.project_state is None:
            return
        self.project_state = replace(
            self.project_state,
            config=replace(self.project_state.config, estilo_capa=normalized),
        )
        self.previews = ()
        self.set_status("Estilo da capa alterado. Atualizando somente a prévia.", "idle")
        self._sync_actions()
        self.request_preview()

    def set_page_appearance(self, background: str, shadow: bool) -> None:
        """Change only internal-page rendering without touching the editorial plan."""
        normalized_background = str(background)
        normalized_shadow = bool(shadow)
        if normalized_background not in {"branco", "cinza", "preto"}:
            raise ValueError("Fundo das páginas inválido.")
        if self.project_state is None:
            return
        current = self.project_state.config
        if self._page_cycle_worker is not None or self._page_cycle_queue:
            self._deferred_page_appearance = (
                None
                if (
                    current.fundo_paginas == normalized_background
                    and current.sombra_fotos == normalized_shadow
                )
                else (normalized_background, normalized_shadow)
            )
            return
        if (
            current.fundo_paginas == normalized_background
            and current.sombra_fotos == normalized_shadow
        ):
            return
        if self.is_busy:
            return
        self._apply_page_appearance(normalized_background, normalized_shadow)
        self.request_preview()

    def _apply_page_appearance(self, background: str, shadow: bool) -> None:
        """Install a validated appearance config while retaining plan and scroll state."""
        if self.project_state is None:
            return
        if self.previews:
            self.preview_grid.pending_scroll_position = (
                self.preview_grid.scroll_area.verticalScrollBar().value()
            )
        config = replace(
            self.project_state.config,
            fundo_paginas=background,
            sombra_fotos=shadow,
        )
        self.project_state = replace(self.project_state, config=config)
        if self._draft_config is not None:
            self._draft_config = replace(
                self._draft_config,
                fundo_paginas=background,
                sombra_fotos=shadow,
            )
        self.sidebar.set_page_appearance(background, shadow, emit=False)
        self.previews = ()
        self.set_status("Aparência das páginas atualizada. Preparando a prévia.", "idle")
        self._sync_actions()

    def set_cover_identity(
        self, identity: dict[str, str], *, request_preview: bool = True
    ) -> None:
        """Update debounced cover identity without regenerating internal pages."""
        values = {
            key: str(identity.get(key, "")).strip()
            for key in ("titulo", "estudio", "site", "logo")
        }
        if self._page_cycle_worker is not None or self._page_cycle_queue:
            self._deferred_cover_identity = values
            return
        if self._draft_config is not None:
            self._draft_config = replace(self._draft_config, **values)
        if self.project_state is None:
            return
        self.project_state = replace(
            self.project_state,
            config=replace(self.project_state.config, **values),
        )
        self.previews = ()
        logo = values["logo"]
        if logo and not Path(logo).is_file():
            self.set_status(
                "O logotipo não foi encontrado. A capa será criada sem ele.", "warning"
            )
        elif logo and not self._logo_is_readable(logo):
            self.set_status(
                "O logotipo não pôde ser lido. A capa será criada sem ele.", "warning"
            )
        else:
            self.set_status("Identidade da capa atualizada. Preparando a prévia.", "idle")
        self._sync_actions()
        if request_preview:
            self.request_preview()

    @staticmethod
    def _logo_is_readable(path: str) -> bool:
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, UnidentifiedImageError):
            return False
        return True

    def begin_operation(self, label: str, cancel_event: threading.Event | None = None) -> None:
        if self.previews:
            self.preview_grid.pending_scroll_position = (
                self.preview_grid.scroll_area.verticalScrollBar().value()
            )
        self.is_busy = True
        self._cancel_event = cancel_event or threading.Event()
        self.sidebar.progress_bar.setValue(0)
        self.sidebar.set_busy(True, label)
        # O esqueleto só faz sentido quando não há nada na tela. Com páginas já
        # visíveis, apagá-las para mostrar quatro retângulos cinzas parece que o
        # trabalho se perdeu — e trocar a capa não toca nas páginas.
        if not self.preview_grid.thumbnail_count:
            self.preview_grid.show_loading(label)
        self.preview_grid.set_busy(True, label)
        self.set_status(label, "loading")
        self._sync_actions()

    def update_operation_progress(self, percent: int, message: str) -> None:
        self.sidebar.progress_bar.setValue(max(0, min(100, int(percent))))
        self.sidebar.progress_label.setText(message)
        self.set_status(message, "loading")

    def cancel_active_operation(self) -> None:
        if self._cancel_event is None:
            return
        if self._page_cycle_worker is not None or self._page_cycle_queue:
            queued = tuple(self._page_cycle_queue)
            self._page_cycle_queue.clear()
            for page_number in queued:
                self._page_cycle_busy.discard(page_number)
                self.preview_grid.set_page_busy(page_number, False)
        workers = tuple(self._workers)
        for worker in workers:
            worker.cancel()
        if not workers:
            self._cancel_event.set()
        self.sidebar.cancel_button.setEnabled(False)
        self.set_status("Cancelamento solicitado. Finalizando a etapa atual…", "loading")

    def _end_operation(self) -> None:
        self.is_busy = False
        self._cancel_event = None
        self.sidebar.set_busy(False)
        self.preview_grid.set_busy(False)
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
        self._page_cycle_aspect_ratios = {
            photo.id: photo.width / photo.height
            for photo in photos
            if photo.width > 0 and photo.height > 0
        }
        self.sidebar.set_cover_style(config.estilo_capa, emit=False)
        self.sidebar.set_cover_identity(config)
        self.sidebar.set_page_appearance(
            config.fundo_paginas, config.sombra_fotos, emit=False
        )
        self.sidebar.set_page_appearance_ready(True)
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
        self._classic_preview_photo_id = ""
        self._classic_preview_target = None
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
        warnings = tuple(getattr(previews, "warnings", ()))
        items = tuple(previews)  # type: ignore[arg-type]
        self.previews = items
        self._classic_preview_photo_id = ""
        self._classic_preview_target = None
        if self.project_state.config.estilo_capa == "classica":
            classic_photo_id = str(getattr(previews, "classic_photo_id", ""))
            raw_target = getattr(previews, "classic_photo_target", None)
            try:
                classic_target = tuple(map(int, raw_target)) if raw_target is not None else None
            except (TypeError, ValueError):
                classic_target = None
            if (
                classic_photo_id
                and classic_target is not None
                and len(classic_target) == 2
                and min(classic_target) > 0
            ):
                self._classic_preview_photo_id = classic_photo_id
                self._classic_preview_target = classic_target
        # A grade guarda as miniaturas convertidas; sem o estilo na chave ela
        # devolveria a imagem anterior quando só a aparência muda.
        plan = self.project_state.plan
        self.preview_grid.set_style_token(
            render_style_fingerprint(
                self.project_state.config.to_motor_config(), plan.mode, plan.seed
            )
        )
        self.preview_grid.set_previews(plan, items)
        self._update_page_cycle_availability()
        self._end_operation()
        if warnings:
            self.set_status(str(warnings[0].message), "warning")
        else:
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

    def request_page_cycle(self, page_number: int) -> None:
        """Queue one local layout change without disturbing the visible preview grid."""
        if (
            self.project_state is None
            or not self.previews
            or self._closing
            or (self.is_busy and self._page_cycle_worker is None)
            or page_number in self._page_cycle_busy
            or not any(page.number == page_number and page.role != "cover" for page in self.project_state.plan.pages)
        ):
            return
        self._page_cycle_busy.add(page_number)
        self.preview_grid.set_page_busy(page_number, True)
        self._page_cycle_queue.append(page_number)
        if not self.is_busy:
            self.is_busy = True
            self._cancel_event = threading.Event()
            self.sidebar.set_busy(True, "Atualizando diagramações…")
            self.set_status("Atualizando diagramações selecionadas…", "loading")
            self._sync_actions()
        self._start_next_page_cycle()

    def _start_next_page_cycle(self) -> None:
        if self._page_cycle_worker is not None or not self._page_cycle_queue or self._closing:
            return
        self._start_page_cycle_worker(self._page_cycle_queue.popleft())

    def _start_page_cycle_worker(self, page_number: int) -> None:
        if self.project_state is None or self._cancel_event is None:
            self._page_cycle_busy.discard(page_number)
            self.preview_grid.set_page_busy(page_number, False)
            self._finish_page_cycle_queue()
            return
        worker = PageCycleWorker(
            self.project_state.config.to_motor_config(),
            self.project_state.plan,
            page_number,
            self._preview_width(),
            self._cancel_event,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        self._page_cycle_worker = worker
        self._page_cycle_thread = thread
        self._threads.add(thread)
        self._workers.add(worker)
        thread.started.connect(worker.run)
        worker.completed.connect(self._page_cycle_completed)
        worker.failed.connect(self._page_cycle_failed)
        worker.cancelled.connect(self._page_cycle_cancelled)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._forget_page_cycle_thread(thread, worker))
        thread.start()

    def _active_page_cycle_number(self) -> int | None:
        worker = self._page_cycle_worker
        page_number = getattr(worker, "page_number", None)
        return page_number if isinstance(page_number, int) else None

    def _release_page_cycle_page(self, page_number: int | None) -> None:
        if page_number is not None:
            self._page_cycle_busy.discard(page_number)
            self.preview_grid.set_page_busy(page_number, False)
        self._page_cycle_worker = None

    def _page_cycle_completed(self, result: object) -> None:
        page_number = self._active_page_cycle_number()
        self._release_page_cycle_page(page_number)
        if not isinstance(result, PageCycleResult) or self.project_state is None:
            self._page_cycle_failed("o motor não retornou a página atualizada")
            return
        try:
            self.project_state = replace(self.project_state, plan=result.plan)
            self._replace_preview_page_plan(result.plan, result.page_number)
            self.preview_grid.replace_page_preview(result.page_number, result.thumbnail)
            self._update_page_cycle_availability({result.page_number})
            self.diagnostics.set_plan(result.plan, failures=self._analysis_failures)
            self.set_status(f"Página {result.page_number} atualizada.", "success")
        except Exception as exc:
            self._page_cycle_failed(str(exc))
            return
        finally:
            close = getattr(result.thumbnail, "close", None)
            if callable(close):
                close()
        self._start_next_page_cycle()
        self._finish_page_cycle_queue()

    def _replace_preview_page_plan(self, plan: BookPlan, page_number: int) -> None:
        """Keep the grid's cache key in sync while retaining its cards and scroll position."""
        replacement = next(page for page in plan.pages if page.number == page_number)
        self.preview_grid._plan = plan
        self.preview_grid._entries = tuple(
            replacement if page.number == page_number else page
            for page in self.preview_grid._entries
        )

    def _page_cycle_failed(self, message: str) -> None:
        page_number = self._active_page_cycle_number()
        self._release_page_cycle_page(page_number)
        detail = message.strip().rstrip(".") or "ocorreu um erro inesperado"
        prefix = "Não foi possível atualizar a página:"
        if detail.startswith(prefix):
            detail = detail.removeprefix(prefix).strip() or "ocorreu um erro inesperado"
        self.set_status(
            f"{prefix} {detail}. A fila continuará.", "error",
        )
        self._start_next_page_cycle()
        self._finish_page_cycle_queue()

    def _page_cycle_cancelled(self) -> None:
        page_number = self._active_page_cycle_number()
        self._release_page_cycle_page(page_number)
        queued = tuple(self._page_cycle_queue)
        self._page_cycle_queue.clear()
        for number in queued:
            self._page_cycle_busy.discard(number)
            self.preview_grid.set_page_busy(number, False)
        self._finish_page_cycle_queue()
        self.set_status("Atualização de páginas cancelada. Você pode tentar novamente.", "idle")

    def _finish_page_cycle_queue(self) -> None:
        if self._page_cycle_worker is not None or self._page_cycle_queue:
            return
        self.is_busy = False
        self._cancel_event = None
        self.sidebar.set_busy(False)
        self.preview_grid.set_busy(False)
        self._sync_actions()
        identity, self._deferred_cover_identity = self._deferred_cover_identity, None
        appearance, self._deferred_page_appearance = self._deferred_page_appearance, None
        if self._closing:
            return
        if identity is None and appearance is None:
            return
        if appearance is not None:
            self._apply_page_appearance(*appearance)
        if identity is not None:
            self.set_cover_identity(identity, request_preview=False)
        self.request_preview()

    def _forget_page_cycle_thread(self, thread: QThread, worker: PageCycleWorker) -> None:
        if self._page_cycle_thread is thread:
            self._page_cycle_thread = None
        self._forget_thread(thread, worker)

    def _page_cycle_ratios_for(self, plan: BookPlan, page_numbers: set[int] | None = None) -> dict[str, float]:
        wanted = {
            photo_id
            for page in plan.pages
            if page_numbers is None or page.number in page_numbers
            for photo_id in page.photo_ids
        }
        for photo_id in wanted - self._page_cycle_aspect_ratios.keys():
            try:
                with Image.open(photo_id) as image:
                    if image.width > 0 and image.height > 0:
                        self._page_cycle_aspect_ratios[photo_id] = image.width / image.height
            except (OSError, UnidentifiedImageError):
                continue
        return {
            photo_id: self._page_cycle_aspect_ratios[photo_id]
            for photo_id in wanted
            if photo_id in self._page_cycle_aspect_ratios
        }

    def _update_page_cycle_availability(self, page_numbers: set[int] | None = None) -> None:
        if self.project_state is None:
            self.preview_grid.set_page_alternatives(())
            return
        plan = self.project_state.plan
        candidates = (
            tuple(page.number for page in plan.pages if page.role != "cover")
            if page_numbers is None
            else tuple(page_numbers)
        )
        available = set(getattr(self.preview_grid, "_alternative_page_numbers", set()))
        if page_numbers is None:
            available.clear()
        for page_number in candidates:
            try:
                ratios = self._page_cycle_ratios_for(plan, {page_number})
                if tem_alternativa(plan, page_number, ratios):
                    available.add(page_number)
                else:
                    available.discard(page_number)
            except ValueError:
                available.discard(page_number)
        self.preview_grid.set_page_alternatives(available)

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
        if self.project_state is None or self.is_busy:
            return
        all_ids = tuple(
            dict.fromkeys(
                (
                    *self.project_state.photo_paths,
                    *(photo_id for page in self.project_state.plan.pages for photo_id in page.photo_ids),
                )
            )
        )
        estilo = self.project_state.config.estilo_capa
        classic = estilo == "classica"
        # Oferecer posições que o estilo não desenha faz o clique parecer perdido.
        uma_foto = fotos_usadas_pela_capa(estilo) == 1
        if classic and self.project_state.config.foto_capa_id:
            selected = (self.project_state.config.foto_capa_id,)
        elif uma_foto:
            selected = self.project_state.plan.cover_photo_ids[:1]
        else:
            selected = self.project_state.plan.cover_photo_ids
        remaining = tuple(photo_id for photo_id in all_ids if photo_id not in selected)
        dialog = CoverDialog(selected, remaining, self, single_selection=uma_foto)
        dialog.replacement_requested.connect(self._cover_replaced)
        dialog.single_photo_selected.connect(
            self.set_classic_cover_photo if classic
            else lambda photo_id: self._cover_replaced(0, photo_id)
        )
        dialog.finished.connect(lambda _result: self._release_cover_dialog(dialog))
        self._cover_dialog = dialog
        dialog.open()

    def _release_cover_dialog(self, dialog: CoverDialog) -> None:
        if self._cover_dialog is dialog:
            self._cover_dialog = None

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

    def set_classic_cover_photo(self, photo_id: str) -> None:
        """Persist one classic-cover photo without changing the multi-photo cover."""
        if self.project_state is None:
            raise ValueError("Analise as fotografias antes de alterar a capa.")
        available = {
            *self.project_state.photo_paths,
            *(photo for page in self.project_state.plan.pages for photo in page.photo_ids),
        }
        if photo_id not in available:
            raise ValueError("A fotografia escolhida não pertence a este projeto.")
        config = replace(
            self.project_state.config,
            foto_capa_id=photo_id,
            capa_foco_x=0.5,
            capa_foco_y=0.5,
            capa_zoom=1.0,
            capa_enquadramento="automatico",
        )
        self.project_state = replace(self.project_state, config=config)
        self.previews = ()
        self.set_status(
            "Fotografia da Capa Clássica escolhida. Preparando a prévia.", "success"
        )
        self._sync_actions()
        self.request_preview()

    def open_crop_dialog(self) -> None:
        if (
            self.project_state is None
            or self.is_busy
            or self.project_state.config.estilo_capa != "classica"
        ):
            return
        if (
            not self.previews
            or not self._classic_preview_photo_id
            or self._classic_preview_target is None
        ):
            self.set_status(
                "Prepare a prévia da Capa Clássica antes de ajustar o enquadramento.",
                "idle",
            )
            self.request_preview()
            return
        photo_path = self._classic_preview_photo_id
        target_size = self._classic_preview_target
        if not os.path.isfile(photo_path):
            self.set_status(
                "A fotografia exibida na prévia não está mais disponível. Atualize a prévia.",
                "error",
            )
            return
        config = self.project_state.config
        value = ClassicCrop(
            config.capa_foco_x,
            config.capa_foco_y,
            config.capa_zoom,
            config.capa_enquadramento,
        )
        try:
            dialog = CropDialog(photo_path, value, target_size, self)
        except ValueError as exc:
            self.set_status(str(exc), "error")
            return
        dialog.applied.connect(
            lambda focus_x, focus_y, zoom: self.set_classic_crop(
                focus_x,
                focus_y,
                zoom,
                mode=dialog.value.mode,
                photo_id=dialog.photo_path,
            )
        )
        dialog.finished.connect(lambda _result: self._release_crop_dialog(dialog))
        self._crop_dialog = dialog
        dialog.open()

    def _release_crop_dialog(self, dialog: CropDialog) -> None:
        if self._crop_dialog is dialog:
            self._crop_dialog = None

    def set_classic_crop(
        self,
        focus_x: float,
        focus_y: float,
        zoom: float,
        *,
        mode: str = "manual",
        photo_id: str | None = None,
    ) -> None:
        """Persist only classic crop fields and render the unchanged plan once."""
        if self.project_state is None:
            raise ValueError("Analise as fotografias antes de ajustar a capa.")
        if mode not in {"automatico", "manual"}:
            raise ValueError("Enquadramento da capa inválido.")
        selected_photo_id = (
            self.project_state.config.foto_capa_id if photo_id is None else str(photo_id)
        )
        if selected_photo_id:
            available = {
                *self.project_state.photo_paths,
                *(photo for page in self.project_state.plan.pages for photo in page.photo_ids),
            }
            if selected_photo_id not in available:
                raise ValueError("A fotografia exibida não pertence a este projeto.")
        config = replace(
            self.project_state.config,
            foto_capa_id=selected_photo_id,
            capa_foco_x=focus_x,
            capa_foco_y=focus_y,
            capa_zoom=zoom,
            capa_enquadramento=mode,
        )
        self.project_state = replace(self.project_state, config=config)
        self.previews = ()
        self.set_status("Enquadramento da Capa Clássica atualizado.", "success")
        self._sync_actions()
        self.request_preview()

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
        default = os.path.join(self.folder_path, f"{recursos.PRODUCT_NAME}.provas.json")
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Salvar projeto",
            default,
            f"Projeto {recursos.PRODUCT_NAME} (*.provas.json);;JSON (*.json)",
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
        self.open_project_button.setEnabled(not self.is_busy)
        self.sidebar.analyze_button.setEnabled(has_folder and not self.is_busy)
        self.sidebar.set_cover_ready(bool(preview_ready))
        self.sidebar.set_crop_ready(
            bool(
                preview_ready
                and self._classic_preview_photo_id
                and self._classic_preview_target is not None
            )
        )
        self.preview_grid.regenerate_button.setEnabled(bool(preview_ready and not self.is_busy))
        self.preview_grid.undo_button.setEnabled(
            bool(has_plan and self.project_state.previous_plan is not None and not self.is_busy)
        )
        self.save_button.setEnabled(bool(has_plan and not self.is_busy))
        self.export_button.setEnabled(bool(preview_ready and not self.is_busy))
        self.estado_mudou.emit()

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
        queued = tuple(self._page_cycle_queue)
        self._page_cycle_queue.clear()
        for page_number in queued:
            self._page_cycle_busy.discard(page_number)
            self.preview_grid.set_page_busy(page_number, False)
        workers = tuple(self._workers)
        for worker in workers:
            worker.cancel()
        if self._cancel_event is not None and not workers:
            self._cancel_event.set()
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
