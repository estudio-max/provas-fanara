"""Dominant, zoomable and lazy page-preview surface."""
from __future__ import annotations

from collections import OrderedDict
from typing import Iterable

from PIL import Image
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..modelos import BookPlan, PagePlan


_ROLE_LABELS = {
    "opening": "Abertura",
    "bridge": "Transição",
    "narrative": "Sequência",
    "detail": "Detalhe",
    "pause": "Pausa",
    "ending": "Encerramento",
}

_BASE_CARD_WIDTH = 300
_MIN_CARD_WIDTH = 190
_GRID_GAP = 20


def _to_qimage(source: object) -> QImage:
    if isinstance(source, QImage):
        return source.copy()
    if isinstance(source, QPixmap):
        return source.toImage()
    if isinstance(source, Image.Image):
        image = source.convert("RGB")
        return QImage(
            image.tobytes("raw", "RGB"),
            image.width,
            image.height,
            image.width * 3,
            QImage.Format.Format_RGB888,
        ).copy()
    raise TypeError("Prévia deve ser uma imagem Pillow, QImage ou QPixmap.")


class LazyPageThumbnail(QFrame):
    """Create a pixmap only when Qt first exposes the page card."""

    def __init__(
        self,
        page: PagePlan,
        role: str,
        image: QImage,
        target_width: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageThumbnail")
        self._source = image
        self._loaded = False
        self._target_width = target_width

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.image_label = QLabel("Carregando página…")
        self.image_label.setObjectName("pageImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(120)
        layout.addWidget(self.image_label)

        footer = QHBoxLayout()
        number = QLabel(f"Página {page.number}")
        number.setObjectName("pageNumber")
        role_label = QLabel(role)
        role_label.setObjectName("pageRole")
        footer.addWidget(number)
        footer.addStretch(1)
        footer.addWidget(role_label)
        layout.addLayout(footer)
        self.set_target_width(target_width)

    def set_target_width(self, width: int) -> None:
        self._target_width = max(190, width)
        image_width = self._target_width - 16
        ratio = self._source.height() / max(1, self._source.width())
        self.image_label.setFixedSize(image_width, round(image_width * ratio))
        self.setFixedWidth(self._target_width)
        if self._loaded:
            self._load_pixmap()

    def _load_pixmap(self) -> None:
        pixmap = QPixmap.fromImage(self._source)
        self.image_label.setPixmap(
            pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.image_label.setText("")
        self._loaded = True

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._loaded:
            self._load_pixmap()


class PreviewGrid(QFrame):
    regenerate_requested = Signal()
    undo_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("previewSurface")
        self._plan: BookPlan | None = None
        self._images: tuple[QImage, ...] = ()
        self._cards: list[LazyPageThumbnail] = []
        self._zoom = 100
        self._laid_out_columns = 0
        self._pixmap_cache: OrderedDict[tuple[object, ...], QImage] = OrderedDict()
        self.pending_scroll_position = 0
        self.empty_message = "Escolher pasta para começar a montar o fotolivro."
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("previewToolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(16, 8, 16, 8)
        bar.setSpacing(8)
        title = QLabel("Prévia do fotolivro")
        title.setObjectName("panelTitle")
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        bar.addWidget(title)
        bar.addStretch(1)

        self.undo_button = QPushButton("Desfazer")
        self.undo_button.setFixedWidth(76)
        self.undo_button.setEnabled(False)
        self.undo_button.setToolTip("Voltar à diagramação anterior")
        self.undo_button.clicked.connect(self.undo_requested)
        self.regenerate_button = QPushButton("Gerar outra diagramação")
        self.regenerate_button.setFixedWidth(176)
        self.regenerate_button.setEnabled(False)
        self.regenerate_button.clicked.connect(self.regenerate_requested)
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setObjectName("squareButton")
        self.zoom_out_button.setAccessibleName("Diminuir zoom")
        self.zoom_out_button.clicked.connect(lambda: self.set_zoom(self._zoom - 10))
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomLabel")
        self.zoom_label.setFixedWidth(44)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setObjectName("squareButton")
        self.zoom_in_button.setAccessibleName("Aumentar zoom")
        self.zoom_in_button.clicked.connect(lambda: self.set_zoom(self._zoom + 10))
        for widget in (
            self.undo_button,
            self.regenerate_button,
            self.zoom_out_button,
            self.zoom_label,
            self.zoom_in_button,
        ):
            bar.addWidget(widget)
        root.addWidget(toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("previewScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("previewContent")
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(24, 24, 24, 32)
        self.grid.setHorizontalSpacing(20)
        self.grid.setVerticalSpacing(24)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setWidget(self.content)
        root.addWidget(self.scroll_area, 1)
        self.show_empty(self.empty_message)

    @property
    def thumbnail_count(self) -> int:
        return len(self._cards)

    @property
    def page_roles(self) -> tuple[str, ...]:
        if self._plan is None:
            return ()
        return tuple(_ROLE_LABELS.get(page.role, page.role.capitalize()) for page in self._plan.pages)

    @property
    def zoom(self) -> int:
        return self._zoom

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._cards.clear()

    def show_empty(self, message: str) -> None:
        self.empty_message = message
        self._clear_grid()
        empty = QFrame()
        empty.setObjectName("emptyState")
        layout = QVBoxLayout(empty)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(8)
        heading = QLabel("Sua mesa está pronta")
        heading.setObjectName("emptyTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copy = QLabel(message)
        copy.setObjectName("mutedText")
        copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copy.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(copy)
        self.grid.addWidget(empty, 0, 0, 1, 1, Qt.AlignmentFlag.AlignCenter)

    def show_loading(self, message: str = "Preparando as páginas…") -> None:
        self._clear_grid()
        for index in range(4):
            skeleton = QFrame()
            skeleton.setObjectName("skeletonPage")
            skeleton.setAccessibleName(message)
            skeleton.setFixedSize(270, 191)
            self.grid.addWidget(skeleton, index // 2, index % 2)

    def set_previews(self, plan: BookPlan, images: Iterable[object]) -> None:
        sources = tuple(images)
        if len(sources) != len(plan.pages):
            raise ValueError("A quantidade de prévias não corresponde às páginas do plano.")
        current_scroll = self.scroll_area.verticalScrollBar().value()
        scroll = (
            self.pending_scroll_position
            if current_scroll == 0 and self.pending_scroll_position > 0
            else current_scroll
        )
        self.pending_scroll_position = scroll
        self._plan = plan
        converted: list[QImage] = []
        for page, source in zip(plan.pages, sources):
            cache_key = (plan.seed, plan.mode, page.number, page.template_id, page.photo_ids)
            cached = self._pixmap_cache.get(cache_key)
            image = cached if cached is not None else _to_qimage(source)
            self._pixmap_cache[cache_key] = image
            self._pixmap_cache.move_to_end(cache_key)
            converted.append(image)
        while len(self._pixmap_cache) > 128:
            self._pixmap_cache.popitem(last=False)
        self._images = tuple(converted)
        self._reflow()
        QTimer.singleShot(0, self, lambda: self._restore_scroll(scroll))

    def _restore_scroll(self, value: int) -> None:
        self.pending_scroll_position = value
        self.scroll_area.verticalScrollBar().setValue(value)

    def _columns(self) -> int:
        margins = self.grid.contentsMargins()
        available = max(
            1,
            self.scroll_area.viewport().width() - margins.left() - margins.right(),
        )
        card_width = self._card_width()
        return max(1, (available + _GRID_GAP) // (card_width + _GRID_GAP))

    def _card_width(self) -> int:
        return max(_MIN_CARD_WIDTH, round(_BASE_CARD_WIDTH * self._zoom / 100))

    def _reflow(self) -> None:
        if self._plan is None or not self._images:
            return
        self._clear_grid()
        columns = self._columns()
        self._laid_out_columns = columns
        card_width = self._card_width()
        for index, (page, image) in enumerate(zip(self._plan.pages, self._images)):
            role = _ROLE_LABELS.get(page.role, page.role.capitalize())
            card = LazyPageThumbnail(page, role, image, card_width)
            self._cards.append(card)
            self.grid.addWidget(card, index // columns, index % columns)

    def set_zoom(self, percent: int) -> None:
        value = max(60, min(150, round(percent / 10) * 10))
        if value == self._zoom:
            return
        scroll = self.scroll_area.verticalScrollBar().value()
        self._zoom = value
        self.zoom_label.setText(f"{value}%")
        self.zoom_out_button.setEnabled(value > 60)
        self.zoom_in_button.setEnabled(value < 150)
        self.pending_scroll_position = scroll
        self._reflow()
        QTimer.singleShot(0, self, lambda: self._restore_scroll(scroll))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if (
            self._plan is not None
            and self._images
            and self._laid_out_columns != self._columns()
        ):
            scroll = self.scroll_area.verticalScrollBar().value()
            self._reflow()
            QTimer.singleShot(0, self, lambda: self._restore_scroll(scroll))
