"""Workflow, output mode and cover controls for the editing desk."""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
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


#: Rótulo → qualidade do motor. Nomeia a finalidade, não o número: quem exporta
#: sabe se vai mandar por e-mail ou levar à gráfica, não que 300 dpi é o certo.
FINALIDADES_DO_PDF = (
    ("Web e e-mail · arquivo leve", "leve"),
    ("Padrão · tela e impressão caseira", "normal"),
    ("Impressão profissional · 300 dpi", "alta"),
)


#: Rótulo e chave de cada estilo, na ordem em que aparecem. Os três primeiros
#: são os originais; os oito seguintes vêm do guia editorial e desenham a
#: própria tipografia.
ESTILOS_DE_CAPA = (
    ("Clássica", "classica"),
    ("Mosaico editorial", "mosaico"),
    ("Curvas editoriais", "curvas_editoriais"),
    ("Jornada · foto e coluna de texto", "jornada"),
    ("Toscana · moldura clássica", "toscana"),
    ("Neon · sangria e título vertical", "neon"),
    ("Fluir · sangria e texto claro", "fluir"),
    ("Ritmos · grade de quatro", "ritmos"),
    ("Fragmentos · colagem diagonal", "fragmentos"),
    ("Contrastes · mosaico e título girado", "contrastes"),
    ("Caminho · três fotos em sequência", "caminho"),
)


class WorkflowSidebar(QFrame):
    folder_requested = Signal()
    analysis_requested = Signal()
    mode_changed = Signal(str)
    cover_requested = Signal()
    crop_requested = Signal()
    cover_style_changed = Signal(str)
    cover_identity_changed = Signal(dict)
    page_appearance_changed = Signal(str, bool)
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
        self.page_appearance_section_label = self._section_label("Aparência das páginas")
        layout.addWidget(self.page_appearance_section_label)
        layout.addSpacing(12)
        page_background_label = QLabel("Fundo")
        page_background_label.setObjectName("fieldLabel")
        layout.addWidget(page_background_label)
        layout.addSpacing(6)
        self.page_background = QComboBox()
        self.page_background.setAccessibleName("Fundo das páginas")
        self.page_background.setAccessibleDescription(
            "Escolha Branco, Cinza ou Preto para as páginas internas"
        )
        self.page_background.setMinimumHeight(36)
        self.page_background.addItem("Branco", "branco")
        self.page_background.addItem("Cinza", "cinza")
        self.page_background.addItem("Preto", "preto")
        self.page_background.currentIndexChanged.connect(self._emit_page_appearance)
        layout.addWidget(self.page_background)
        layout.addSpacing(8)
        self.photo_shadow = QCheckBox("Sombra suave nas fotos")
        self.photo_shadow.setAccessibleName("Sombra suave nas fotos")
        self.photo_shadow.setAccessibleDescription(
            "Adiciona uma sombra curta e discreta atrás das fotografias internas"
        )
        self.photo_shadow.setMinimumHeight(36)
        self.photo_shadow.toggled.connect(self._emit_page_appearance)
        layout.addWidget(self.photo_shadow)
        layout.addSpacing(12)
        finalidade_label = QLabel("Finalidade do PDF")
        finalidade_label.setObjectName("fieldLabel")
        layout.addWidget(finalidade_label)
        layout.addSpacing(6)
        # Só vale na exportação: a prévia é sempre leve, porque a resolução do
        # arquivo final não muda a diagramação nem o que se vê na tela.
        self.export_purpose = QComboBox()
        self.export_purpose.setAccessibleName("Finalidade do PDF exportado")
        self.export_purpose.setAccessibleDescription(
            "Define a resolução e a compressão do arquivo exportado"
        )
        self.export_purpose.setMinimumHeight(36)
        for rotulo, chave in FINALIDADES_DO_PDF:
            self.export_purpose.addItem(rotulo, chave)
        self.export_purpose.setCurrentIndex(1)
        layout.addWidget(self.export_purpose)

        self._page_appearance_ready = False
        self._page_appearance_busy = False
        self._update_page_appearance_controls()

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
        for rotulo, chave in ESTILOS_DE_CAPA:
            self.cover_style.addItem(rotulo, chave)
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
        # A prévia já não reabre as fotografias a cada mudança de identidade —
        # elas ficam preparadas em memória e só a capa é redesenhada. Com o
        # trabalho barato, a espera pode ser a de uma pausa curta na digitação.
        self._identity_timer.setInterval(300)
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
        self.crop_button.setProperty("ready", False)
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

    def _emit_page_appearance(self, *_args: object) -> None:
        self.page_appearance_changed.emit(
            str(self.page_background.currentData()), self.photo_shadow.isChecked()
        )

    def _identity_payload(self) -> dict[str, str]:
        return {
            "titulo": self.title_edit.text().strip(),
            "estudio": self.studio_edit.text().strip(),
            "site": self.site_edit.text().strip(),
            "logo": self.logo_path,
        }

    def identity_values(self) -> dict[str, str]:
        """O que está preenchido agora. A barra é a fonte da verdade da identidade."""
        return self._identity_payload()

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

    def set_page_appearance(
        self, background: str, shadow: bool, *, emit: bool = False
    ) -> None:
        index = self.page_background.findData(background)
        if index < 0:
            raise ValueError("Fundo das páginas inválido.")
        blockers = (
            self.page_background.blockSignals(True),
            self.photo_shadow.blockSignals(True),
        )
        self.page_background.setCurrentIndex(index)
        self.photo_shadow.setChecked(bool(shadow))
        self.page_background.blockSignals(blockers[0])
        self.photo_shadow.blockSignals(blockers[1])
        if emit:
            self._emit_page_appearance()

    def set_page_appearance_ready(self, ready: bool) -> None:
        self._page_appearance_ready = bool(ready)
        self._update_page_appearance_controls()

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
        self._page_appearance_busy = bool(busy)
        self.progress_panel.setVisible(busy)
        self.folder_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy and bool(self.folder_label.toolTip()))
        self.proof_radio.setEnabled(not busy)
        self.book_radio.setEnabled(not busy)
        self.cover_button.setEnabled(not busy and self.cover_button.property("ready") is True)
        self.crop_button.setEnabled(
            not busy
            and self.crop_button.property("ready") is True
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
        self._update_page_appearance_controls()
        self.cancel_button.setEnabled(busy)
        if busy and label:
            self.progress_label.setText(label)
        elif not busy:
            self.progress_label.clear()
            self.progress_bar.setValue(0)

    def set_cover_ready(self, ready: bool) -> None:
        self.cover_button.setProperty("ready", ready)
        if not ready:
            self.crop_button.setProperty("ready", False)
        self._update_cover_actions()

    def set_crop_ready(self, ready: bool) -> None:
        self.crop_button.setProperty("ready", ready)
        self._update_cover_actions()

    def _update_cover_actions(self) -> None:
        ready = self.cover_button.property("ready") is True
        available = ready and not self.cancel_button.isEnabled()
        self.cover_button.setEnabled(available)
        self.crop_button.setEnabled(
            self.crop_button.property("ready") is True
            and not self.cancel_button.isEnabled()
            and self.cover_style.currentData() == "classica"
        )

    def _update_page_appearance_controls(self) -> None:
        available = self._page_appearance_ready and not self._page_appearance_busy
        self.page_background.setEnabled(available)
        self.photo_shadow.setEnabled(available)
