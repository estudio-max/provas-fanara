"""Focused cover-photo replacement dialog."""
from __future__ import annotations

import os
from collections.abc import Iterable

from PySide6.QtCore import QSize, QTimer, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import imagens
from .preview_grid import _to_qimage


class ThumbnailListWidget(QListWidget):
    """Load icons only for photo rows that intersect the list viewport."""

    _PATH_ROLE = int(Qt.ItemDataRole.UserRole)
    _LOADED_ROLE = _PATH_ROLE + 1

    def __init__(self, paths: Iterable[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setIconSize(QSize(88, 64))
        self.setUniformItemSizes(True)
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(self._PATH_ROLE, path)
            item.setData(self._LOADED_ROLE, False)
            self.addItem(item)
        self.verticalScrollBar().valueChanged.connect(
            lambda _value: QTimer.singleShot(0, self, self._load_visible)
        )

    @property
    def loaded_thumbnail_count(self) -> int:
        return sum(bool(self.item(index).data(self._LOADED_ROLE)) for index in range(self.count()))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self, self._load_visible)

    def _load_visible(self) -> None:
        viewport_rect = self.viewport().rect()
        for index in range(self.count()):
            item = self.item(index)
            if item.data(self._LOADED_ROLE) or not viewport_rect.intersects(self.visualItemRect(item)):
                continue
            path = str(item.data(self._PATH_ROLE))
            source = None
            thumbnail = None
            try:
                label = os.path.splitext(os.path.basename(path))[0]
                source = imagens.abrir(imagens.Foto(path, label))
                thumbnail = imagens.redimensionar(source, 176)
                item.setIcon(QIcon(QPixmap.fromImage(_to_qimage(thumbnail))))
            except Exception:
                continue
            finally:
                if thumbnail is not None and thumbnail is not source:
                    thumbnail.close()
                if source is not None:
                    source.close()
            item.setData(self._LOADED_ROLE, True)


class CoverDialog(QDialog):
    replacement_requested = Signal(int, str)
    single_photo_selected = Signal(str)

    def __init__(
        self,
        selected: Iterable[str],
        remaining: Iterable[str],
        parent: QWidget | None = None,
        *,
        single_selection: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("coverDialog")
        self.single_selection = bool(single_selection)
        self.setWindowTitle(
            "Escolher foto da capa" if self.single_selection else "Trocar fotos da capa"
        )
        self.setModal(True)
        self.resize(760, 500)
        self._selected = tuple(selected)
        self._remaining = (
            tuple(dict.fromkeys((*self._selected, *tuple(remaining))))
            if self.single_selection
            else tuple(remaining)
        )
        self._submitted = False
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)
        self.intro_label = QLabel(
            "Escolha a fotografia da capa. A seleção é independente dos outros estilos."
            if self.single_selection
            else (
                "Escolha uma posição da capa e uma fotografia disponível. "
                "A substituição mantém a ordem dos demais espaços."
            )
        )
        self.intro_label.setWordWrap(True)
        root.addWidget(self.intro_label)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        selected_column = QVBoxLayout()
        selected_title = QLabel("Na capa")
        selected_title.setObjectName("sectionTitle")
        selected_column.addWidget(selected_title)
        self.selected_list = ThumbnailListWidget(self._selected)
        self.selected_list.setAccessibleName("Fotografias selecionadas para a capa")
        for index in range(self.selected_list.count()):
            item = self.selected_list.item(index)
            item.setText(f"{index + 1}. {item.text()}")
        selected_column.addWidget(self.selected_list)
        if self.single_selection:
            selected_title.hide()
            self.selected_list.hide()
        else:
            columns.addLayout(selected_column, 1)

        remaining_column = QVBoxLayout()
        remaining_title = QLabel(
            "Fotografias do projeto" if self.single_selection else "Fotografias disponíveis"
        )
        remaining_title.setObjectName("sectionTitle")
        remaining_column.addWidget(remaining_title)
        self.remaining_list = ThumbnailListWidget(self._remaining)
        self.remaining_list.setAccessibleName(
            "Fotografias disponíveis para a capa"
            if self.single_selection
            else "Fotografias disponíveis para substituição"
        )
        remaining_column.addWidget(self.remaining_list)
        columns.addLayout(remaining_column, 1)
        root.addLayout(columns, 1)

        self.replace_button = QPushButton(
            "Escolher fotografia" if self.single_selection else "Substituir fotografia"
        )
        self.replace_button.setObjectName("primaryButton")
        self.replace_button.setEnabled(False)
        self.replace_button.clicked.connect(self._replace)
        self.selected_list.currentRowChanged.connect(lambda _row: self._update_action())
        self.remaining_list.currentRowChanged.connect(lambda _row: self._update_action())
        self.remaining_list.itemDoubleClicked.connect(lambda _item: self._replace())
        root.addWidget(self.replace_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _update_action(self) -> None:
        self.replace_button.setEnabled(
            not self._submitted
            and self.remaining_list.currentRow() >= 0
            and (self.single_selection or self.selected_list.currentRow() >= 0)
        )

    def _replace(self) -> None:
        if self._submitted:
            return
        source = self.remaining_list.currentRow()
        if source < 0:
            return
        slot = self.selected_list.currentRow()
        if not self.single_selection and slot < 0:
            return
        self._submitted = True
        self.replace_button.setEnabled(False)
        if self.single_selection:
            self.single_photo_selected.emit(self._remaining[source])
            self.accept()
            return
        self.replacement_requested.emit(slot, self._remaining[source])
        self.accept()
