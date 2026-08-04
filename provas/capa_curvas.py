"""Geometria determinística da capa curva ``Órbita equilibrada``.

Este módulo conhece somente regiões normalizadas e máscaras em escala de
cinza. Associação de fotos, enquadramento e identidade pertencem às etapas
posteriores do compositor de capa.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from PIL import Image, ImageDraw


_SUPERSAMPLING = 3
MIN_ORBIT_WIDTH = 16
MIN_ORBIT_HEIGHT = 11
_IDENTITY_SAFE = (0.38, 0.34, 0.24, 0.30)
_LOGO_SAFE = (0.04, 0.05, 0.18, 0.09)
_SITE_SAFE = (0.78, 0.90, 0.18, 0.05)


@dataclass(frozen=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def intersection(self, other: "PixelRect") -> "PixelRect":
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        return PixelRect(left, top, max(0, right - left), max(0, bottom - top))


@dataclass(frozen=True)
class CurveSlot:
    id: str
    path: tuple[tuple[float, float], ...]
    bounds: PixelRect
    preferred_focus: tuple[float, float]


@dataclass(frozen=True)
class CurveLayout:
    slots: tuple[CurveSlot, ...]
    identity_safe_rect: PixelRect
    logo_rect: PixelRect
    site_rect: PixelRect


@dataclass(frozen=True)
class _NormalizedSlot:
    id: str
    path: tuple[tuple[float, float], ...]
    bounds: tuple[float, float, float, float]
    preferred_focus: tuple[float, float]


def _cubic_point(
    start: tuple[float, float],
    control_a: tuple[float, float],
    control_b: tuple[float, float],
    end: tuple[float, float],
    position: float,
) -> tuple[float, float]:
    inverse = 1.0 - position
    return (
        inverse**3 * start[0]
        + 3 * inverse**2 * position * control_a[0]
        + 3 * inverse * position**2 * control_b[0]
        + position**3 * end[0],
        inverse**3 * start[1]
        + 3 * inverse**2 * position * control_a[1]
        + 3 * inverse * position**2 * control_b[1]
        + position**3 * end[1],
    )


def _leaf_path(
    bounds: tuple[float, float, float, float],
    *,
    mirror_x: bool = False,
    mirror_y: bool = False,
) -> tuple[tuple[float, float], ...]:
    """Create a sampled four-Bézier leaf contained by normalized bounds."""
    segments = (
        ((0.00, 0.22), (0.20, 0.04), (0.48, 0.00), (0.70, 0.00)),
        ((0.70, 0.00), (0.92, 0.08), (1.00, 0.30), (1.00, 0.55)),
        ((1.00, 0.55), (0.90, 0.78), (0.60, 1.00), (0.22, 1.00)),
        ((0.22, 1.00), (0.04, 0.90), (0.00, 0.55), (0.00, 0.22)),
    )
    local_points: list[tuple[float, float]] = []
    for segment in segments:
        for step in range(24):
            local_points.append(_cubic_point(*segment, step / 24))
    local_points.append(segments[-1][-1])

    x, y, width, height = bounds
    result = []
    for local_x, local_y in local_points:
        if mirror_x:
            local_x = 1.0 - local_x
        if mirror_y:
            local_y = 1.0 - local_y
        result.append((x + local_x * width, y + local_y * height))
    return tuple(result)


def _slot(
    identifier: str,
    bounds: tuple[float, float, float, float],
    *,
    mirror_x: bool = False,
    mirror_y: bool = False,
    focus: tuple[float, float] = (0.5, 0.42),
) -> _NormalizedSlot:
    return _NormalizedSlot(
        identifier,
        _leaf_path(bounds, mirror_x=mirror_x, mirror_y=mirror_y),
        bounds,
        focus,
    )


_RAW_VARIANTS: dict[int, tuple[_NormalizedSlot, ...]] = {
    1: (
        _slot("hero_left", (0.02, 0.06, 0.33, 0.88), focus=(0.46, 0.40)),
    ),
    2: (
        _slot("hero_left", (0.02, 0.06, 0.33, 0.88), focus=(0.46, 0.40)),
        _slot("hero_right", (0.65, 0.06, 0.33, 0.88), mirror_x=True, focus=(0.54, 0.40)),
    ),
    3: (
        _slot("hero_left", (0.02, 0.05, 0.34, 0.87), focus=(0.46, 0.40)),
        _slot("hero_right", (0.64, 0.05, 0.34, 0.87), mirror_x=True, focus=(0.54, 0.40)),
        _slot("lower_arc", (0.30, 0.70, 0.40, 0.28), mirror_y=True, focus=(0.50, 0.36)),
    ),
    4: (
        _slot("hero_left", (0.02, 0.20, 0.34, 0.72), focus=(0.46, 0.40)),
        _slot("hero_right", (0.64, 0.18, 0.34, 0.74), mirror_x=True, focus=(0.54, 0.40)),
        _slot("upper_arc", (0.28, 0.03, 0.44, 0.27), mirror_x=True, focus=(0.50, 0.55)),
        _slot("lower_arc", (0.29, 0.70, 0.42, 0.27), mirror_y=True, focus=(0.50, 0.35)),
    ),
    5: (
        _slot("left_upper", (0.02, 0.04, 0.34, 0.42), focus=(0.46, 0.45)),
        _slot("left_lower", (0.02, 0.53, 0.34, 0.43), mirror_y=True, focus=(0.46, 0.35)),
        _slot("right_upper", (0.64, 0.03, 0.34, 0.43), mirror_x=True, focus=(0.54, 0.45)),
        _slot("right_lower", (0.64, 0.52, 0.34, 0.44), mirror_x=True, mirror_y=True, focus=(0.54, 0.35)),
        _slot("lower_arc", (0.31, 0.69, 0.38, 0.29), mirror_y=True, focus=(0.50, 0.35)),
    ),
    6: (
        _slot("upper_left", (0.03, 0.03, 0.44, 0.27), focus=(0.45, 0.52)),
        _slot("upper_right", (0.53, 0.03, 0.44, 0.27), mirror_x=True, focus=(0.55, 0.52)),
        _slot("side_left", (0.02, 0.28, 0.33, 0.41), focus=(0.46, 0.42)),
        _slot("side_right", (0.65, 0.28, 0.33, 0.41), mirror_x=True, focus=(0.54, 0.42)),
        _slot("lower_left", (0.03, 0.70, 0.44, 0.27), mirror_y=True, focus=(0.45, 0.34)),
        _slot("lower_right", (0.53, 0.70, 0.44, 0.27), mirror_x=True, mirror_y=True, focus=(0.55, 0.34)),
    ),
    7: (
        _slot("upper_left", (0.03, 0.03, 0.44, 0.27), focus=(0.45, 0.52)),
        _slot("upper_right", (0.53, 0.03, 0.44, 0.27), mirror_x=True, focus=(0.55, 0.52)),
        _slot("side_left", (0.02, 0.28, 0.33, 0.41), focus=(0.46, 0.42)),
        _slot("side_right", (0.65, 0.28, 0.33, 0.41), mirror_x=True, focus=(0.54, 0.42)),
        _slot("lower_left", (0.03, 0.70, 0.29, 0.27), mirror_y=True, focus=(0.45, 0.34)),
        _slot("lower_center", (0.355, 0.69, 0.29, 0.28), mirror_x=True, mirror_y=True, focus=(0.50, 0.34)),
        _slot("lower_right", (0.68, 0.70, 0.29, 0.27), mirror_x=True, mirror_y=True, focus=(0.55, 0.34)),
    ),
    8: (
        _slot("upper_left", (0.03, 0.03, 0.29, 0.27), focus=(0.45, 0.52)),
        _slot("upper_center", (0.355, 0.02, 0.29, 0.28), mirror_x=True, focus=(0.50, 0.52)),
        _slot("upper_right", (0.68, 0.03, 0.29, 0.27), mirror_x=True, focus=(0.55, 0.52)),
        _slot("side_left", (0.02, 0.28, 0.33, 0.41), focus=(0.46, 0.42)),
        _slot("side_right", (0.65, 0.28, 0.33, 0.41), mirror_x=True, focus=(0.54, 0.42)),
        _slot("lower_left", (0.03, 0.70, 0.29, 0.27), mirror_y=True, focus=(0.45, 0.34)),
        _slot("lower_center", (0.355, 0.69, 0.29, 0.28), mirror_x=True, mirror_y=True, focus=(0.50, 0.34)),
        _slot("lower_right", (0.68, 0.70, 0.29, 0.27), mirror_x=True, mirror_y=True, focus=(0.55, 0.34)),
    ),
    9: (
        _slot("upper_left", (0.03, 0.03, 0.29, 0.27), focus=(0.45, 0.52)),
        _slot("upper_center", (0.355, 0.02, 0.29, 0.28), mirror_x=True, focus=(0.50, 0.52)),
        _slot("upper_right", (0.68, 0.03, 0.29, 0.27), mirror_x=True, focus=(0.55, 0.52)),
        _slot("side_left", (0.02, 0.28, 0.33, 0.41), focus=(0.46, 0.42)),
        _slot("side_right", (0.65, 0.28, 0.33, 0.41), mirror_x=True, focus=(0.54, 0.42)),
        _slot("lower_left", (0.02, 0.70, 0.23, 0.27), mirror_y=True, focus=(0.45, 0.34)),
        _slot("lower_center_left", (0.265, 0.70, 0.225, 0.27), mirror_x=True, mirror_y=True, focus=(0.48, 0.34)),
        _slot("lower_center_right", (0.51, 0.70, 0.225, 0.27), mirror_y=True, focus=(0.52, 0.34)),
        _slot("lower_right", (0.75, 0.70, 0.23, 0.27), mirror_x=True, mirror_y=True, focus=(0.55, 0.34)),
    ),
}

ORBIT_VARIANTS: Mapping[int, tuple[_NormalizedSlot, ...]] = MappingProxyType(_RAW_VARIANTS)
del _RAW_VARIANTS


def _scale_rect(
    normalized: tuple[float, float, float, float], width: int, height: int
) -> PixelRect:
    x, y, normalized_width, normalized_height = normalized
    left = round(x * width)
    top = round(y * height)
    right = round((x + normalized_width) * width)
    bottom = round((y + normalized_height) * height)
    return PixelRect(left, top, right - left, bottom - top)


def layout_orbita(width: int, height: int, count: int) -> CurveLayout:
    """Scale an immutable normalized orbit variant to a landscape canvas."""
    if width <= 0 or height <= 0 or width <= height or not 1 <= count <= 9:
        raise ValueError(
            "A órbita exige dimensões positivas em A4 horizontal e de 1 a 9 fotografias."
        )
    if width < MIN_ORBIT_WIDTH or height < MIN_ORBIT_HEIGHT:
        raise ValueError("A órbita exige no mínimo 16×11 pixels para manter todas as fotos visíveis.")

    slots = tuple(
        CurveSlot(
            definition.id,
            definition.path,
            _scale_rect(definition.bounds, width, height),
            definition.preferred_focus,
        )
        for definition in ORBIT_VARIANTS[count]
    )
    return CurveLayout(
        slots,
        _scale_rect(_IDENTITY_SAFE, width, height),
        _scale_rect(_LOGO_SAFE, width, height),
        _scale_rect(_SITE_SAFE, width, height),
    )


def render_mask(slot: CurveSlot, size: tuple[int, int]) -> Image.Image:
    """Rasterize one normalized Bézier path at 3× and reduce with LANCZOS."""
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError("A máscara exige dimensões positivas.")

    scale = _SUPERSAMPLING
    mask = Image.new("L", (width * scale, height * scale), 0)
    points = tuple(
        (round(x * width * scale), round(y * height * scale)) for x, y in slot.path
    )
    ImageDraw.Draw(mask).polygon(points, fill=255)
    reduced = mask.resize((width, height), Image.Resampling.LANCZOS)
    clipped = Image.new("L", (width, height), 0)
    crop_box = (slot.bounds.x, slot.bounds.y, slot.bounds.right, slot.bounds.bottom)
    clipped.paste(reduced.crop(crop_box), crop_box[:2])
    return clipped
