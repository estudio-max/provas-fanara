"""Dominant, zoomable and lazy page-preview surface."""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Collection, Iterable

from PIL import Image
from PySide6.QtCore import QRect, QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
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
    "cover": "Capa",
    "opening": "Abertura",
    "bridge": "Transição",
    "narrative": "Sequência",
    "sequence": "Sequência",
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
        self.page_number = page.number
        self._source = image
        self._loaded = False
        self._target_width = target_width
        self._reload_available = False
        self._reload_busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.image_label = QLabel("Carregando página…")
        self.image_label.setObjectName("pageImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(120)

        self.reload_button: QPushButton | None = None
        control_strip = QWidget()
        control_strip.setFixedHeight(28)
        controls = QHBoxLayout(control_strip)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addStretch(1)
        if page.role != "cover":
            self.reload_button = QPushButton("↻")
            self.reload_button.setObjectName("pageReloadButton")
            self.reload_button.setFixedSize(28, 28)
            self.reload_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.reload_button.setAutoDefault(False)
            action = f"Mudar diagramação da página {page.number}"
            self.reload_button.setAccessibleName(action)
            self.reload_button.setToolTip(action)
            self.reload_button.clicked.connect(
                lambda _checked=False, number=page.number: self.reload_requested.emit(number)
            )
            controls.addWidget(self.reload_button)
        layout.addWidget(control_strip)
        layout.addWidget(self.image_label)

        footer = QHBoxLayout()
        number = QLabel("Capa" if page.role == "cover" else f"Página {page.number}")
        number.setObjectName("pageNumber")
        role_label = QLabel(role)
        role_label.setObjectName("pageRole")
        footer.addWidget(number)
        footer.addStretch(1)
        footer.addWidget(role_label)
        layout.addLayout(footer)
        self.set_target_width(target_width)

    reload_requested = Signal(int)

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

    def replace_preview(self, image: QImage) -> None:
        """Swap only this card's source bitmap without reflowing the grid."""
        self._source = image
        if self._loaded:
            self._load_pixmap()

    def set_reload_available(self, available: bool) -> None:
        self._reload_available = available
        self._sync_reload_button()

    def set_reload_busy(self, busy: bool) -> None:
        self._reload_busy = busy
        self._sync_reload_button()

    def _sync_reload_button(self) -> None:
        if self.reload_button is None:
            return
        busy = self._reload_busy
        self.reload_button.setEnabled(self._reload_available and not busy)
        self.reload_button.setText("…" if busy else "↻")
        self.reload_button.setProperty("busy", busy)
        self.reload_button.setAccessibleDescription(
            f"Atualizando diagramação da página {self.page_number}" if busy else ""
        )
        self.reload_button.style().unpolish(self.reload_button)
        self.reload_button.style().polish(self.reload_button)

    def materialize(self) -> None:
        if not self._loaded:
            self._load_pixmap()


class PreviewGrid(QFrame):
    regenerate_requested = Signal()
    undo_requested = Signal()
    page_layout_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("previewSurface")
        self._plan: BookPlan | None = None
        self._entries: tuple[PagePlan, ...] = ()
        self._images: tuple[QImage, ...] = ()
        self._cards: list[LazyPageThumbnail] = []
        self._zoom = 100
        self._laid_out_columns = 0
        self._pixmap_cache: OrderedDict[tuple[object, ...], QImage] = OrderedDict()
        self._alternative_page_numbers: set[int] = set()
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
        self.scroll_area.verticalScrollBar().valueChanged.connect(
            lambda _value: self._schedule_visible_materialization()
        )
        root.addWidget(self.scroll_area, 1)
        self.show_empty(self.empty_message)

    @property
    def thumbnail_count(self) -> int:
        return len(self._cards)

    @property
    def page_roles(self) -> tuple[str, ...]:
        return tuple(_ROLE_LABELS.get(page.role, page.role.capitalize()) for page in self._entries)

    @property
    def page_labels(self) -> tuple[str, ...]:
        return tuple("Capa" if page.role == "cover" else f"Página {page.number}" for page in self._entries)

    @property
    def materialized_thumbnail_count(self) -> int:
        return sum(card._loaded for card in self._cards)

    @property
    def zoom(self) -> int:
        return self._zoom

    def card(self, page_number: int) -> LazyPageThumbnail:
        """Return the stable card instance for a displayed page."""
        for card in self._cards:
            if card.page_number == page_number:
                return card
        raise KeyError(f"Página {page_number} não está visível na prévia.")

    def set_page_alternatives(self, page_numbers: Collection[int]) -> None:
        """Enable the local layout action only for pages that can change."""
        internal_numbers = {
            page.number for page in self._entries if page.role != "cover"
        }
        self._alternative_page_numbers = set(page_numbers) & internal_numbers
        for card in self._cards:
            card.set_reload_available(card.page_number in self._alternative_page_numbers)

    def set_page_busy(self, page_number: int, busy: bool) -> None:
        """Show a discreet in-place busy state for one internal page action."""
        try:
            card = self.card(page_number)
        except KeyError:
            return
        card.set_reload_busy(busy)

    def replace_page_preview(self, page_number: int, image: Image.Image) -> None:
        """Replace one rendered bitmap while preserving card, scroll and layout state."""
        for index, page in enumerate(self._entries):
            if page.number != page_number:
                continue
            converted = _to_qimage(image)
            images = list(self._images)
            images[index] = converted
            self._images = tuple(images)
            if self._plan is not None and page.role != "cover":
                cache_key = self._cache_key(page)
                self._pixmap_cache[cache_key] = converted
                self._pixmap_cache.move_to_end(cache_key)
                while len(self._pixmap_cache) > 128:
                    self._pixmap_cache.popitem(last=False)
            self.card(page_number).replace_preview(converted)
            return
        raise ValueError(f"Página {page_number} não está visível na prévia.")

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._cards.clear()

    def _cache_key(self, page: PagePlan) -> tuple[object, ...]:
        if self._plan is None:
            raise RuntimeError("Não há plano para indexar a prévia.")
        return (
            self._plan.seed,
            self._plan.mode,
            page.number,
            page.template_id,
            page.photo_ids,
        )

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
        if len(sources) == len(plan.pages) + 1:
            entries = (PagePlan(0, "cover", plan.cover_photo_ids, "cover"), *plan.pages)
        elif len(sources) == len(plan.pages):
            entries = plan.pages
        else:
            raise ValueError("A quantidade de prévias não corresponde às páginas do plano.")
        current_scroll = self.scroll_area.verticalScrollBar().value()
        scroll = (
            self.pending_scroll_position
            if current_scroll == 0 and self.pending_scroll_position > 0
            else current_scroll
        )
        self.pending_scroll_position = scroll
        self._plan = plan
        self._entries = tuple(entries)
        self._alternative_page_numbers.clear()
        converted: list[QImage] = []
        for page, source in zip(self._entries, sources):
            if page.role == "cover":
                image = _to_qimage(source)
            else:
                cache_key = self._cache_key(page)
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
        self._schedule_visible_materialization()

    def _restore_scroll(self, value: int) -> None:
        self.pending_scroll_position = value
        self.scroll_area.verticalScrollBar().setValue(value)
        self._materialize_visible_cards()

    def _schedule_visible_materialization(self) -> None:
        QTimer.singleShot(0, self, self._materialize_visible_cards)

    def _materialize_visible_cards(self) -> None:
        if not self._cards:
            return
        scrollbar = self.scroll_area.verticalScrollBar()
        visible = QRect(
            0,
            scrollbar.value(),
            self.scroll_area.viewport().width(),
            self.scroll_area.viewport().height(),
        )
        for card in self._cards:
            if visible.intersects(card.geometry()):
                card.materialize()

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
        for index, (page, image) in enumerate(zip(self._entries, self._images)):
            role = _ROLE_LABELS.get(page.role, page.role.capitalize())
            card = LazyPageThumbnail(page, role, image, card_width)
            card.reload_requested.connect(self.page_layout_requested)
            card.set_reload_available(page.number in self._alternative_page_numbers)
            self._cards.append(card)
            self.grid.addWidget(card, index // columns, index % columns)
            card.show()
        self.grid.activate()
        self.content.adjustSize()
        self._schedule_visible_materialization()

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
        else:
            self._schedule_visible_materialization()
