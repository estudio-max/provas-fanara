"""Focused cover-photo replacement dialog."""
from __future__ import annotations

import os
from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CoverDialog(QDialog):
    replacement_requested = Signal(int, str)

    def __init__(
        self,
        selected: Iterable[str],
        remaining: Iterable[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("coverDialog")
        self.setWindowTitle("Trocar fotos da capa")
        self.setModal(True)
        self.resize(760, 500)
        self._selected = tuple(selected)
        self._remaining = tuple(remaining)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)
        intro = QLabel(
            "Escolha uma posição da capa e uma fotografia disponível. "
            "A substituição mantém a ordem dos demais espaços."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        selected_column = QVBoxLayout()
        selected_column.addWidget(QLabel("Na capa"))
        self.selected_list = QListWidget()
        self.selected_list.setAccessibleName("Fotografias selecionadas para a capa")
        for index, photo_id in enumerate(self._selected, start=1):
            self.selected_list.addItem(f"{index}. {os.path.basename(photo_id)}")
        selected_column.addWidget(self.selected_list)
        columns.addLayout(selected_column, 1)

        remaining_column = QVBoxLayout()
        remaining_column.addWidget(QLabel("Fotografias disponíveis"))
        self.remaining_list = QListWidget()
        self.remaining_list.setAccessibleName("Fotografias disponíveis para substituição")
        for photo_id in self._remaining:
            self.remaining_list.addItem(os.path.basename(photo_id))
        remaining_column.addWidget(self.remaining_list)
        columns.addLayout(remaining_column, 1)
        root.addLayout(columns, 1)

        self.replace_button = QPushButton("Substituir fotografia")
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
            self.selected_list.currentRow() >= 0 and self.remaining_list.currentRow() >= 0
        )

    def _replace(self) -> None:
        slot = self.selected_list.currentRow()
        source = self.remaining_list.currentRow()
        if slot < 0 or source < 0:
            return
        self.replacement_requested.emit(slot, self._remaining[source])
        self.accept()
