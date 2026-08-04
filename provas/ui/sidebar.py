"""Workflow, output mode and cover controls for the editing desk."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class WorkflowSidebar(QFrame):
    folder_requested = Signal()
    analysis_requested = Signal()
    mode_changed = Signal(str)
    cover_requested = Signal()
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
        layout = QVBoxLayout(self)
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
        layout.addWidget(self._section_label("Capa"))
        layout.addSpacing(8)
        cover_copy = QLabel("Revise a seleção automática sem alterar a ordem do álbum.")
        cover_copy.setObjectName("mutedText")
        cover_copy.setWordWrap(True)
        layout.addWidget(cover_copy)
        layout.addSpacing(12)

        self.cover_button = QPushButton("Trocar fotos da capa")
        self.cover_button.setEnabled(False)
        self.cover_button.clicked.connect(self.cover_requested)
        layout.addWidget(self.cover_button)

        layout.addStretch(1)

        self.progress_panel = QFrame()
        self.progress_panel.setObjectName("progressPanel")
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)
        self.progress_label = QLabel("Preparando a mesa…")
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

    @property
    def mode(self) -> str:
        return "prova" if self.proof_radio.isChecked() else "fotolivro"

    def set_folder(self, path: str) -> None:
        self.folder_label.setText(os.path.basename(path.rstrip("\\/")) or path)
        self.folder_label.setToolTip(path)

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
        self.folder_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy and bool(self.folder_label.toolTip()))
        self.proof_radio.setEnabled(not busy)
        self.book_radio.setEnabled(not busy)
        self.cover_button.setEnabled(not busy and self.cover_button.property("ready") is True)
        self.cancel_button.setEnabled(busy)
        if label:
            self.progress_label.setText(label)

    def set_cover_ready(self, ready: bool) -> None:
        self.cover_button.setProperty("ready", ready)
        self.cover_button.setEnabled(ready and not self.cancel_button.isEnabled())
