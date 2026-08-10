"""Transactional editor for the single-photo classic-cover crop."""
from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import enquadramento, imagens
from ..capa_classica import (
    ClassicCrop,
    classic_photo_target,
    crop_box,
    resolve_classic_crop_box,
)
from .preview_grid import _to_qimage


class CropCanvas(QWidget):
    """Paint and edit a local crop draft without mutating project state."""

    crop_changed = Signal(object)

    def __init__(
        self,
        image,
        crop: ClassicCrop,
        faces: tuple[enquadramento.FaceBox, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cropCanvas")
        self.setAccessibleName("Prévia do enquadramento da capa")
        self.setAccessibleDescription(
            "Arraste a fotografia ou use as setas para ajustar o enquadramento."
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMinimumSize(480, 294)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image = _to_qimage(image)
        if self._image.isNull():
            raise ValueError("A fotografia da capa não pôde ser lida.")
        self._faces = tuple(faces)
        self._crop = self._normalized(crop)
        self._last_position: QPoint | None = None

    @property
    def crop(self) -> ClassicCrop:
        return self._crop

    @property
    def source_size(self) -> tuple[int, int]:
        return (self._image.width(), self._image.height())

    @staticmethod
    def _normalized(crop: ClassicCrop) -> ClassicCrop:
        return ClassicCrop(
            min(1.0, max(0.0, float(crop.focus_x))),
            min(1.0, max(0.0, float(crop.focus_y))),
            min(2.5, max(1.0, float(crop.zoom))),
            crop.mode if crop.mode in {"automatico", "manual"} else "automatico",
        )

    def _frame_rect(self) -> QRectF:
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        target_width, target_height = classic_photo_target()
        ratio = target_width / target_height
        width = area.width()
        height = width / ratio
        if height > area.height():
            height = area.height()
            width = height * ratio
        return QRectF(
            area.center().x() - width / 2,
            area.center().y() - height / 2,
            width,
            height,
        )

    def _display_box(self):
        if self._crop.mode == "automatico":
            return resolve_classic_crop_box(
                self.source_size,
                classic_photo_target(),
                self._crop,
                self._faces,
            )
        return crop_box(self.source_size, classic_photo_target(), self._crop)

    def _effective_manual_crop(self) -> ClassicCrop:
        box = self._display_box()
        width, height = self.source_size
        return ClassicCrop(
            (box.left + box.right) / (2 * width),
            (box.top + box.bottom) / (2 * height),
            self._crop.zoom,
            "manual",
        )

    def _bounded_focus(self, focus_x: float, focus_y: float, zoom: float) -> tuple[float, float]:
        width, height = self.source_size
        centered = crop_box(
            self.source_size,
            classic_photo_target(),
            ClassicCrop(0.5, 0.5, zoom, "manual"),
        )
        margin_x = centered.width / (2 * width)
        margin_y = centered.height / (2 * height)
        return (
            min(1.0 - margin_x, max(margin_x, focus_x)),
            min(1.0 - margin_y, max(margin_y, focus_y)),
        )

    def set_zoom(self, zoom: float) -> None:
        current = self._effective_manual_crop()
        normalized_zoom = min(2.5, max(1.0, float(zoom)))
        focus_x, focus_y = self._bounded_focus(
            current.focus_x,
            current.focus_y,
            normalized_zoom,
        )
        self._set_crop(ClassicCrop(focus_x, focus_y, normalized_zoom, "manual"))

    def reset_automatic(self) -> None:
        self._set_crop(ClassicCrop())

    def _set_crop(self, crop: ClassicCrop) -> None:
        normalized = self._normalized(crop)
        if normalized == self._crop:
            return
        self._crop = normalized
        self.crop_changed.emit(normalized)
        self.update()

    def _drag(self, dx: float, dy: float) -> None:
        frame = self._frame_rect()
        if frame.width() <= 0 or frame.height() <= 0:
            return
        current = self._effective_manual_crop()
        box = crop_box(self.source_size, classic_photo_target(), current)
        width, height = self.source_size
        focus_x = current.focus_x - dx * box.width / (frame.width() * width)
        focus_y = current.focus_y - dy * box.height / (frame.height() * height)
        focus_x, focus_y = self._bounded_focus(focus_x, focus_y, current.zoom)
        self._set_crop(ClassicCrop(focus_x, focus_y, current.zoom, "manual"))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._frame_rect().contains(event.position()):
            self._last_position = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            position = event.position().toPoint()
            delta = position - self._last_position
            self._last_position = position
            self._drag(delta.x(), delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._last_position is not None:
            self._last_position = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        directions = {
            Qt.Key.Key_Left: (8, 0),
            Qt.Key.Key_Right: (-8, 0),
            Qt.Key.Key_Up: (0, 8),
            Qt.Key.Key_Down: (0, -8),
        }
        if event.key() in directions:
            dx, dy = directions[event.key()]
            multiplier = 4 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            self._drag(dx * multiplier, dy * multiplier)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111215"))
        frame = self._frame_rect()
        box = self._display_box()
        source = QRectF(box.left, box.top, box.width, box.height)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(frame, self._image, source)
        border = QColor("#E04C6B") if self.hasFocus() else QColor("#4A4B55")
        painter.setPen(QPen(border, 2 if self.hasFocus() else 1))
        painter.drawRect(frame)
        painter.end()


class CropDialog(QDialog):
    """Edit a classic crop as a draft and publish it only through Apply."""

    applied = Signal(float, float, float)

    def __init__(
        self,
        photo_path: str,
        value: ClassicCrop,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cropDialog")
        self.setWindowTitle("Ajustar enquadramento")
        self.setModal(True)
        self.resize(760, 570)
        self.setMinimumSize(620, 500)
        self._committed_value = value
        self._applied = False

        source = None
        try:
            source = imagens.abrir(
                imagens.Foto(photo_path, os.path.splitext(os.path.basename(photo_path))[0])
            )
            try:
                faces = tuple(enquadramento.detect_faces(source))
            except RuntimeError:
                faces = ()
            image = _to_qimage(source)
        except Exception as exc:
            raise ValueError(
                "A fotografia da capa não pôde ser lida. Escolha outra fotografia e tente novamente."
            ) from exc
        finally:
            if source is not None:
                source.close()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("Ajuste a fotografia dentro da área da capa")
        title.setObjectName("panelTitle")
        root.addWidget(title)
        help_text = QLabel(
            "Arraste para reposicionar. O recorte sempre cobre toda a moldura e só será salvo ao aplicar."
        )
        help_text.setObjectName("mutedText")
        help_text.setWordWrap(True)
        root.addWidget(help_text)

        self.canvas = CropCanvas(image, value, faces)
        root.addWidget(self.canvas, 1)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        zoom_title = QLabel("Zoom")
        zoom_title.setObjectName("fieldLabel")
        controls.addWidget(zoom_title)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setObjectName("cropZoom")
        self.zoom_slider.setAccessibleName("Zoom do enquadramento")
        self.zoom_slider.setRange(100, 250)
        self.zoom_slider.setSingleStep(5)
        self.zoom_slider.setPageStep(10)
        self.zoom_slider.setValue(round(value.zoom * 100))
        controls.addWidget(self.zoom_slider, 1)
        self.zoom_label = QLabel(f"{self.zoom_slider.value()}%")
        self.zoom_label.setObjectName("zoomLabel")
        self.zoom_label.setMinimumWidth(44)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        controls.addWidget(self.zoom_label)
        root.addLayout(controls)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.automatic_button = QPushButton("Enquadramento automático")
        self.automatic_button.setAccessibleName("Restaurar enquadramento automático")
        actions.addWidget(self.automatic_button)
        actions.addStretch(1)
        self.cancel_button = QPushButton("Cancelar")
        self.apply_button = QPushButton("Aplicar")
        self.apply_button.setObjectName("dialogApplyButton")
        self.apply_button.setDefault(True)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.apply_button)
        root.addLayout(actions)

        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        self.canvas.crop_changed.connect(self._crop_changed)
        self.automatic_button.clicked.connect(self._reset_automatic)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self._apply)

    @property
    def value(self) -> ClassicCrop:
        return self.canvas.crop

    @property
    def committed_value(self) -> ClassicCrop:
        return self._committed_value

    def _zoom_changed(self, percent: int) -> None:
        self.zoom_label.setText(f"{percent}%")
        self.canvas.set_zoom(percent / 100)

    def _crop_changed(self, crop: ClassicCrop) -> None:
        percent = round(crop.zoom * 100)
        if self.zoom_slider.value() != percent:
            blocked = self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(percent)
            self.zoom_slider.blockSignals(blocked)
        self.zoom_label.setText(f"{percent}%")

    def _reset_automatic(self) -> None:
        self.canvas.reset_automatic()

    def _apply(self) -> None:
        if self._applied:
            return
        self._applied = True
        crop = self.canvas.crop
        self._committed_value = crop
        self.apply_button.setEnabled(False)
        self.applied.emit(crop.focus_x, crop.focus_y, crop.zoom)
        self.accept()
