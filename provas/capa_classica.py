"""Compositor puro da capa clássica com uma única fotografia.

O módulo recebe uma foto já aberta, compõe pixels e devolve uma ``Capa``. Ele
não conhece configuração de UI, documentos, exportação ou persistência.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import enquadramento
from .capa_curvas import PixelRect
from .capas import Capa, CoverPhoto
from .identidade_capa import CoverTextOverflow


_DESIGN_SIZE = (1600, 1131)
_TITLE_MAX_PT = 34
_TITLE_MIN_PT = 22
_STUDIO_PT = 10
_STUDIO_TRACKING_PT = 3
_OVERFLOW_MESSAGE = "O título da capa não cabe. Abrevie o título antes de exportar."

BODONI_PATH = str(
    Path(__file__).resolve().parents[1] / "assets" / "fonts" / "BodoniModa[opsz,wght].ttf"
)
_SEGOE_UI_LIGHT_PATH = str(
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeuil.ttf"
)


@dataclass(frozen=True)
class ClassicCrop:
    focus_x: float = 0.5
    focus_y: float = 0.5
    zoom: float = 1.0
    mode: str = "automatico"


class _ClassicRect(PixelRect):
    """``PixelRect`` com os aliases editoriais left/top usados pela capa."""

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y


@dataclass(frozen=True)
class _CropBox:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True)
class ClassicLayout:
    title: PixelRect
    studio: PixelRect
    photo: PixelRect


def layout_classico(width: int, height: int) -> ClassicLayout:
    """Escalone as proporções aprovadas para qualquer canvas positivo."""
    if width <= 0 or height <= 0:
        raise ValueError("A capa clássica exige dimensões positivas.")
    return ClassicLayout(
        _ClassicRect(
            round(width * 0.08),
            round(height * 0.061),
            round(width * 0.84),
            round(height * 0.061),
        ),
        _ClassicRect(
            round(width * 0.08),
            round(height * 0.141),
            round(width * 0.84),
            round(height * 0.030),
        ),
        _ClassicRect(
            round(width * 0.08),
            round(height * 0.187),
            round(width * 0.84),
            round(height * (0.916 - 0.187)),
        ),
    )


def _finite_clamped(value: float, lower: float, upper: float, fallback: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(numeric):
        return fallback
    return min(upper, max(lower, numeric))


def crop_box(
    source_size: tuple[int, int],
    target_size: tuple[int, int],
    crop: ClassicCrop,
) -> _CropBox:
    """Calcule crop-to-fill fracionário, zoomado e limitado à foto."""
    source_width, source_height = source_size
    target_width, target_height = target_size
    if min(source_width, source_height, target_width, target_height) <= 0:
        raise ValueError("O recorte da capa exige dimensões positivas.")
    if crop.mode not in ("automatico", "manual"):
        raise ValueError("Enquadramento da capa inválido.")

    source_ratio = source_width / source_height
    target_ratio = target_width / target_height
    if source_ratio >= target_ratio:
        base_height = float(source_height)
        base_width = base_height * target_ratio
    else:
        base_width = float(source_width)
        base_height = base_width / target_ratio

    zoom = _finite_clamped(crop.zoom, 1.0, 2.5, 1.0)
    box_width = base_width / zoom
    box_height = base_height / zoom
    focus_x = _finite_clamped(crop.focus_x, 0.0, 1.0, 0.5) * source_width
    focus_y = _finite_clamped(crop.focus_y, 0.0, 1.0, 0.5) * source_height
    left = min(source_width - box_width, max(0.0, focus_x - box_width / 2.0))
    top = min(source_height - box_height, max(0.0, focus_y - box_height / 2.0))
    return _CropBox(left, top, left + box_width, top + box_height)


def _scale_for(width: int, height: int) -> float:
    return min(width / _DESIGN_SIZE[0], height / _DESIGN_SIZE[1])


def _fit_title(title: str, available_width: int, scale: float):
    with Image.new("L", (1, 1), 0) as measure:
        draw = ImageDraw.Draw(measure)
        largest = max(1, round(_TITLE_MAX_PT * scale))
        smallest = max(1, round(_TITLE_MIN_PT * scale))
        for size in range(largest, smallest - 1, -1):
            font = ImageFont.truetype(BODONI_PATH, size)
            bounds = draw.textbbox((0, 0), title, font=font)
            if bounds[2] - bounds[0] <= available_width:
                return font, bounds
    raise CoverTextOverflow(_OVERFLOW_MESSAGE)


def _studio_font(size: int):
    try:
        return ImageFont.truetype(_SEGOE_UI_LIGHT_PATH, size)
    except OSError:
        return ImageFont.truetype(BODONI_PATH, size)


def _tracking_width(draw: ImageDraw.ImageDraw, text: str, font, tracking: int) -> float:
    glyphs = [draw.textlength(character, font=font) for character in text]
    return sum(glyphs) + max(0, len(glyphs) - 1) * tracking


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    rect: _ClassicRect,
    text: str,
    font,
    bounds: tuple[int, int, int, int],
) -> None:
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    position = (
        rect.left + (rect.width - text_width) / 2 - bounds[0],
        rect.top + (rect.height - text_height) / 2 - bounds[1],
    )
    draw.text(position, text, fill=(17, 17, 17), font=font)


def _draw_tracked_studio(
    draw: ImageDraw.ImageDraw,
    rect: _ClassicRect,
    text: str,
    font,
    tracking: int,
) -> None:
    total_width = _tracking_width(draw, text, font, tracking)
    bounds = draw.textbbox((0, 0), text or " ", font=font)
    x = rect.left + (rect.width - total_width) / 2
    y = rect.top + (rect.height - (bounds[3] - bounds[1])) / 2 - bounds[1]
    for character in text:
        draw.text((x, y), character, fill=(35, 35, 35), font=font)
        x += draw.textlength(character, font=font) + tracking


def _automatic_crop(source: Image.Image, requested: ClassicCrop) -> ClassicCrop:
    faces = tuple(
        face
        for face in enquadramento.detect_faces(source)
        if face.confidence >= enquadramento.MIN_FACE_CONFIDENCE
    )
    if not faces:
        return requested
    weights = tuple(max(face.width * face.height * face.confidence, 1e-12) for face in faces)
    total = sum(weights)
    focus_x = sum(face.center[0] * weight for face, weight in zip(faces, weights)) / total
    focus_y = sum(face.center[1] * weight for face, weight in zip(faces, weights)) / total
    return ClassicCrop(focus_x, focus_y, requested.zoom, requested.mode)


def render_classic_cover(
    photo: CoverPhoto,
    width: int,
    height: int,
    title: str,
    studio: str,
    crop: ClassicCrop,
) -> Capa:
    """Componha uma capa sem fechar ou alterar a fotografia do chamador."""
    layout = layout_classico(width, height)
    scale = _scale_for(width, height)
    title_font, title_bounds = _fit_title(title, layout.title.width, scale)
    studio_font = _studio_font(max(1, round(_STUDIO_PT * scale)))
    tracking = max(0, round(_STUDIO_TRACKING_PT * scale))

    if not isinstance(photo, CoverPhoto) or not isinstance(photo.image, Image.Image):
        raise ValueError("Forneça uma fotografia de capa válida.")
    photo.image.load()
    effective_crop = _automatic_crop(photo.image, crop) if crop.mode == "automatico" else crop
    source_box = crop_box(
        photo.image.size,
        (layout.photo.width, layout.photo.height),
        effective_crop,
    )

    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    try:
        with photo.image.convert("RGB") as rgb:
            with rgb.transform(
                (layout.photo.width, layout.photo.height),
                Image.Transform.EXTENT,
                (source_box.left, source_box.top, source_box.right, source_box.bottom),
                resample=Image.Resampling.BICUBIC,
            ) as framed:
                canvas.paste(framed, (layout.photo.left, layout.photo.top))
        draw = ImageDraw.Draw(canvas)
        _draw_centered_text(draw, layout.title, title, title_font, title_bounds)
        _draw_tracked_studio(draw, layout.studio, studio, studio_font, tracking)
        return Capa(
            canvas,
            0.0,
            identity_embedded=True,
            used_photo_ids=(photo.id,),
        )
    except BaseException:
        canvas.close()
        raise
