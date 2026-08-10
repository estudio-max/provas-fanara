"""Workflow, output mode and cover controls for the editing desk."""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class WorkflowSidebar(QFrame):
    folder_requested = Signal()
    analysis_requested = Signal()
    mode_changed = Signal(str)
    cover_requested = Signal()
    crop_requested = Signal()
    cover_style_changed = Signal(str)
    cover_identity_changed = Signal(dict)
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workflowSidebar")
        self.setFixedWidth(265)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._build()

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _build(self) -> None:
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("sidebarScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("sidebarContent")
        content.setMinimumWidth(244)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(0)

        layout.addWidget(self._section_label("Fluxo de trabalho"))
        layout.addSpacing(12)

        self.folder_button = QPushButton("Escolher pasta")
        self.folder_button.setObjectName("importantButton")
        self.folder_button.setAccessibleName("Escolher pasta de fotografias")
        self.folder_button.clicked.connect(self.folder_requested)
        layout.addWidget(self.folder_button)

        self.folder_label = QLabel("Nenhuma pasta escolhida")
        self.folder_label.setObjectName("mutedText")
        self.folder_label.setWordWrap(True)
        self.folder_label.setMinimumHeight(36)
        layout.addSpacing(8)
        layout.addWidget(self.folder_label)

        self.analyze_button = QPushButton("Analisar fotografias")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.analysis_requested)
        layout.addSpacing(8)
        layout.addWidget(self.analyze_button)

        layout.addSpacing(24)
        layout.addWidget(self._section_label("Tipo de saída"))
        layout.addSpacing(12)

        self.proof_radio = QRadioButton("Prova para seleção")
        self.book_radio = QRadioButton("Fotolivro limpo")
        self.proof_radio.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.proof_radio)
        self.mode_group.addButton(self.book_radio)
        layout.addWidget(self.proof_radio)
        layout.addSpacing(4)
        layout.addWidget(self.book_radio)

        self.mode_description = QLabel()
        self.mode_description.setObjectName("mutedText")
        self.mode_description.setWordWrap(True)
        self.mode_description.setMinimumHeight(52)
        layout.addSpacing(8)
        layout.addWidget(self.mode_description)
        self.proof_radio.toggled.connect(
            lambda checked: checked and self.mode_changed.emit("prova")
        )
        self.book_radio.toggled.connect(
            lambda checked: checked and self.mode_changed.emit("fotolivro")
        )
        self.set_mode("prova", emit=False)

        layout.addSpacing(24)
        self.cover_section_label = self._section_label("Capa")
        layout.addWidget(self.cover_section_label)
        layout.addSpacing(12)
        style_label = QLabel("Estilo")
        style_label.setObjectName("fieldLabel")
        layout.addWidget(style_label)
        layout.addSpacing(6)
        self.cover_style = QComboBox()
        self.cover_style.setAccessibleName("Estilo da capa")
        self.cover_style.addItem("Clássica", "classica")
        self.cover_style.addItem("Mosaico editorial", "mosaico")
        self.cover_style.addItem("Curvas editoriais", "curvas_editoriais")
        self.cover_style.currentIndexChanged.connect(self._emit_cover_style)
        layout.addWidget(self.cover_style)

        self.title_edit = self._identity_edit("Título", "Título da capa")
        self.studio_edit = self._identity_edit(
            "Fotógrafo / estúdio", "Nome do fotógrafo ou estúdio"
        )
        self.site_edit = self._identity_edit("Site", "Site do fotógrafo ou estúdio")
        for label, edit in (
            ("Título", self.title_edit),
            ("Fotógrafo / estúdio", self.studio_edit),
            ("Site", self.site_edit),
        ):
            layout.addSpacing(12)
            field_label = QLabel(label)
            field_label.setObjectName("fieldLabel")
            layout.addWidget(field_label)
            layout.addSpacing(6)
            layout.addWidget(edit)

        layout.addSpacing(12)
        logo_label = QLabel("Logotipo")
        logo_label.setObjectName("fieldLabel")
        layout.addWidget(logo_label)
        layout.addSpacing(6)
        self.logo_path = ""
        logo_row = QHBoxLayout()
        logo_row.setSpacing(8)
        self.logo_choose_button = QPushButton("Escolher…")
        self.logo_choose_button.setAccessibleName("Escolher logotipo da capa")
        self.logo_choose_button.clicked.connect(self._choose_logo)
        self.logo_remove_button = QPushButton("Remover")
        self.logo_remove_button.setAccessibleName("Remover logotipo da capa")
        self.logo_remove_button.setEnabled(False)
        self.logo_remove_button.clicked.connect(self._remove_logo)
        logo_row.addWidget(self.logo_choose_button, 1)
        logo_row.addWidget(self.logo_remove_button)
        layout.addLayout(logo_row)
        self.logo_name = QLabel("Nenhum logotipo")
        self.logo_name.setObjectName("mutedText")
        self.logo_name.setWordWrap(True)
        layout.addSpacing(6)
        layout.addWidget(self.logo_name)

        self._identity_timer = QTimer(self)
        self._identity_timer.setSingleShot(True)
        self._identity_timer.setInterval(250)
        self._identity_timer.timeout.connect(self._emit_cover_identity)
        for edit in (self.title_edit, self.studio_edit, self.site_edit):
            edit.textChanged.connect(lambda _text: self._identity_timer.start())

        layout.addSpacing(16)

        self.cover_button = QPushButton("Trocar fotos da capa")
        self.cover_button.setEnabled(False)
        self.cover_button.clicked.connect(self.cover_requested)
        layout.addWidget(self.cover_button)

        layout.addSpacing(8)
        self.crop_button = QPushButton("Ajustar enquadramento")
        self.crop_button.setAccessibleName("Ajustar enquadramento")
        self.crop_button.setToolTip("Reposicionar e ampliar a fotografia da Capa Clássica")
        self.crop_button.setEnabled(False)
        self.crop_button.clicked.connect(self.crop_requested)
        layout.addWidget(self.crop_button)

        layout.addStretch(1)

        self.progress_panel = QFrame()
        self.progress_panel.setObjectName("progressPanel")
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("mutedText")
        self.progress_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_requested)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.cancel_button)
        layout.addWidget(self.progress_panel)
        self.progress_panel.hide()
        # End breathing room lets keyboard/scroll navigation align the cover group
        # as a coherent section instead of leaving a clipped prior label above it.
        layout.addSpacing(30)
        self.scroll_area.setWidget(content)
        shell.addWidget(self.scroll_area)

    @staticmethod
    def _identity_edit(placeholder: str, accessible_name: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setAccessibleName(accessible_name)
        edit.setMinimumHeight(36)
        return edit

    def _emit_cover_style(self) -> None:
        self._update_cover_actions()
        self.cover_style_changed.emit(str(self.cover_style.currentData()))

    def _identity_payload(self) -> dict[str, str]:
        return {
            "titulo": self.title_edit.text().strip(),
            "estudio": self.studio_edit.text().strip(),
            "site": self.site_edit.text().strip(),
            "logo": self.logo_path,
        }

    def _emit_cover_identity(self) -> None:
        self.cover_identity_changed.emit(self._identity_payload())

    def _choose_logo(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Escolher logotipo", "", "Imagens (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self.logo_path = path
            self.logo_name.setText(os.path.basename(path))
            self.logo_name.setToolTip(path)
            self.logo_remove_button.setEnabled(True)
            self._identity_timer.start()

    def _remove_logo(self) -> None:
        self.logo_path = ""
        self.logo_name.setText("Nenhum logotipo")
        self.logo_name.setToolTip("")
        self.logo_remove_button.setEnabled(False)
        self._identity_timer.start()

    def set_cover_style(self, style: str, *, emit: bool = False) -> None:
        index = self.cover_style.findData(style)
        if index < 0:
            raise ValueError("Estilo de capa inválido.")
        blocked = self.cover_style.blockSignals(True)
        self.cover_style.setCurrentIndex(index)
        self.cover_style.blockSignals(blocked)
        self._update_cover_actions()
        if emit:
            self.cover_style_changed.emit(style)

    def set_cover_identity(self, config: object) -> None:
        self._identity_timer.stop()
        edits = (self.title_edit, self.studio_edit, self.site_edit)
        blockers = tuple(edit.blockSignals(True) for edit in edits)
        self.title_edit.setText(str(getattr(config, "titulo", "")))
        self.studio_edit.setText(str(getattr(config, "estudio", "")))
        self.site_edit.setText(str(getattr(config, "site", "")))
        for edit, blocked in zip(edits, blockers):
            edit.blockSignals(blocked)
        self.logo_path = str(getattr(config, "logo", ""))
        self.logo_name.setText(os.path.basename(self.logo_path) if self.logo_path else "Nenhum logotipo")
        self.logo_name.setToolTip(self.logo_path)
        self.logo_remove_button.setEnabled(bool(self.logo_path))

    @property
    def mode(self) -> str:
        return "prova" if self.proof_radio.isChecked() else "fotolivro"

    def set_folder(self, path: str) -> None:
        self.folder_label.setText(os.path.basename(path.rstrip("\\/")) or path)
        self.folder_label.setToolTip(path)

    def set_project_loaded(self, loaded: bool) -> None:
        """Keep folder selection primary only until a project has been built."""
        self.folder_button.setText("Trocar pasta" if loaded else "Escolher pasta")
        self.folder_button.setObjectName("secondaryButton" if loaded else "importantButton")
        self.folder_button.style().unpolish(self.folder_button)
        self.folder_button.style().polish(self.folder_button)

    def set_mode(self, mode: str, *, emit: bool = False) -> None:
        if mode not in {"prova", "fotolivro"}:
            raise ValueError("Modo deve ser 'prova' ou 'fotolivro'.")
        target = self.proof_radio if mode == "prova" else self.book_radio
        blockers = (self.proof_radio.blockSignals(True), self.book_radio.blockSignals(True))
        target.setChecked(True)
        self.proof_radio.blockSignals(blockers[0])
        self.book_radio.blockSignals(blockers[1])
        self.mode_description.setText(
            "Prova para seleção · marca d’água e códigos das fotografias."
            if mode == "prova"
            else "Fotolivro limpo · imagens sem marca d’água nem códigos."
        )
        if emit:
            self.mode_changed.emit(mode)

    def set_busy(self, busy: bool, label: str = "") -> None:
        self.progress_panel.setVisible(busy)
        self.folder_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy and bool(self.folder_label.toolTip()))
        self.proof_radio.setEnabled(not busy)
        self.book_radio.setEnabled(not busy)
        self.cover_button.setEnabled(not busy and self.cover_button.property("ready") is True)
        self.crop_button.setEnabled(
            not busy
            and self.cover_button.property("ready") is True
            and self.cover_style.currentData() == "classica"
        )
        for control in (
            self.cover_style,
            self.title_edit,
            self.studio_edit,
            self.site_edit,
            self.logo_choose_button,
        ):
            control.setEnabled(not busy)
        self.logo_remove_button.setEnabled(not busy and bool(self.logo_path))
        self.cancel_button.setEnabled(busy)
        if busy and label:
            self.progress_label.setText(label)
        elif not busy:
            self.progress_label.clear()
            self.progress_bar.setValue(0)

    def set_cover_ready(self, ready: bool) -> None:
        self.cover_button.setProperty("ready", ready)
        self._update_cover_actions()

    def _update_cover_actions(self) -> None:
        ready = self.cover_button.property("ready") is True
        available = ready and not self.cancel_button.isEnabled()
        self.cover_button.setEnabled(available)
        self.crop_button.setEnabled(
            available and self.cover_style.currentData() == "classica"
        )
