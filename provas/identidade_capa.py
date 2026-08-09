"""Identidade tipográfica da capa curva editorial."""
from __future__ import annotations

import os
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from . import tema
from .capa_curvas import CurveLayout, PixelRect


_DESIGN_SIZE = (1600, 1131)
_TITLE_SIZES = tuple(range(54, 31, -2))
_STUDIO_SIZES = tuple(range(26, 17, -1))
_SITE_SIZES = tuple(range(18, 13, -1))
_LOGO_MISSING = "O logotipo não foi encontrado; a capa foi criada sem ele."
_LOGO_UNREADABLE = "O logotipo não pôde ser lido; a capa foi criada sem ele."
_OVERFLOW_MESSAGE = "O texto da capa não cabe. Abrevie o conteúdo antes de exportar."
_MINIMUM_LOGO_CONTRAST = 4.5


@dataclass(frozen=True)
class IdentityData:
    title: str
    studio: str
    site: str
    logo_path: str = ""


@dataclass(frozen=True)
class CoverWarning:
    code: str
    message: str


class CoverTextOverflow(ValueError):
    """Raised when cover copy cannot fit its reserved safe region."""


def _rgb(color: tema.Cor) -> tuple[int, int, int]:
    return tuple(round(channel * 255) for channel in color)  # type: ignore[return-value]


def _relative_luminance(color: tuple[int, int, int]) -> float:
    channels = tuple(channel / 255 for channel in color)
    linear = tuple(
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: float, second: float) -> float:
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def _enforce_logo_contrast(
    logo: Image.Image,
    background: Image.Image,
) -> None:
    corrected_pixels = []
    changed = False
    for logo_pixel, background_pixel in zip(
        logo.get_flattened_data(),
        background.get_flattened_data(),
    ):
        red, green, blue, alpha = logo_pixel
        if alpha:
            logo_luminance = _relative_luminance((red, green, blue))
            background_luminance = _relative_luminance(background_pixel)
            if (
                _contrast_ratio(logo_luminance, background_luminance)
                < _MINIMUM_LOGO_CONTRAST
            ):
                dark_contrast = _contrast_ratio(0.0, background_luminance)
                light_contrast = _contrast_ratio(1.0, background_luminance)
                color = (
                    (0, 0, 0)
                    if dark_contrast >= light_contrast
                    else (255, 255, 255)
                )
                logo_pixel = (*color, alpha)
                changed = True
        corrected_pixels.append(logo_pixel)
    if changed:
        logo.putdata(corrected_pixels)


def _scale_for(canvas: Image.Image) -> float:
    return min(canvas.width / _DESIGN_SIZE[0], canvas.height / _DESIGN_SIZE[1])


def _font(source: tema.Fonte, size: int) -> ImageFont.ImageFont:
    if source.arquivo:
        try:
            return ImageFont.truetype(source.arquivo, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _bounds(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font)


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    source: tema.Fonte,
    design_sizes: tuple[int, ...],
    rect: PixelRect,
    scale: float,
) -> tuple[ImageFont.ImageFont, tuple[int, int, int, int]]:
    for design_size in design_sizes:
        font = _font(source, max(1, round(design_size * scale)))
        bounds = _bounds(draw, text, font)
        if bounds[2] - bounds[0] <= rect.width and bounds[3] - bounds[1] <= rect.height:
            return font, bounds
    raise CoverTextOverflow(_OVERFLOW_MESSAGE)


def _font_options(
    draw: ImageDraw.ImageDraw,
    text: str,
    source: tema.Fonte,
    design_sizes: tuple[int, ...],
    rect: PixelRect,
    scale: float,
) -> tuple[tuple[ImageFont.ImageFont, tuple[int, int, int, int]], ...]:
    options = []
    for design_size in design_sizes:
        font = _font(source, max(1, round(design_size * scale)))
        bounds = _bounds(draw, text, font)
        if bounds[2] - bounds[0] <= rect.width and bounds[3] - bounds[1] <= rect.height:
            options.append((font, bounds))
    if text and not options:
        raise CoverTextOverflow(_OVERFLOW_MESSAGE)
    return tuple(options)


def _identity_lines(
    draw: ImageDraw.ImageDraw,
    title: str,
    studio: str,
    rect: PixelRect,
    scale: float,
) -> tuple[tuple[str, ImageFont.ImageFont, tuple[int, int, int, int]], ...]:
    title_options = (
        _font_options(draw, title, tema.SERIF, _TITLE_SIZES, rect, scale)
        if title
        else ((None, None),)
    )
    studio_options = (
        _font_options(draw, studio, tema.SANS_MEDIO, _STUDIO_SIZES, rect, scale)
        if studio
        else ((None, None),)
    )
    gap = max(1, round(18 * scale)) if title and studio else 0
    for title_font, title_bounds in title_options:
        for studio_font, studio_bounds in studio_options:
            height = gap
            if title_bounds is not None:
                height += title_bounds[3] - title_bounds[1]
            if studio_bounds is not None:
                height += studio_bounds[3] - studio_bounds[1]
            if height <= rect.height:
                lines = []
                if title_font is not None and title_bounds is not None:
                    lines.append((title, title_font, title_bounds))
                if studio_font is not None and studio_bounds is not None:
                    lines.append((studio, studio_font, studio_bounds))
                return tuple(lines)
    raise CoverTextOverflow(_OVERFLOW_MESSAGE)


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    rect: PixelRect,
    text: str,
    font: ImageFont.ImageFont,
    bounds: tuple[int, int, int, int],
    fill: tuple[int, int, int],
) -> None:
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x = rect.x + (rect.width - width) // 2 - bounds[0]
    y = rect.y + (rect.height - height) // 2 - bounds[1]
    draw.text((x, y), text, font=font, fill=fill)


def _draw_identity_lines(
    draw: ImageDraw.ImageDraw,
    rect: PixelRect,
    lines: tuple[tuple[str, ImageFont.ImageFont, tuple[int, int, int, int]], ...],
    fills: tuple[tuple[int, int, int], ...],
    scale: float,
) -> None:
    gap = max(1, round(18 * scale)) if len(lines) == 2 else 0
    heights = tuple(bounds[3] - bounds[1] for _, _, bounds in lines)
    cursor_y = rect.y + (rect.height - sum(heights) - gap) // 2
    for index, ((text, font, bounds), fill) in enumerate(zip(lines, fills)):
        width = bounds[2] - bounds[0]
        x = rect.x + (rect.width - width) // 2 - bounds[0]
        draw.text((x, cursor_y - bounds[1]), text, font=font, fill=fill)
        cursor_y += heights[index] + gap


def _prepare_logo(
    path: str,
    rect: PixelRect,
    canvas: Image.Image,
) -> tuple[Image.Image | None, tuple[CoverWarning, ...]]:
    clean_path = path.strip()
    if not clean_path or not os.path.isfile(clean_path):
        return None, (CoverWarning("logo_ausente", _LOGO_MISSING),)
    logo: Image.Image | None = None
    try:
        with Image.open(clean_path) as opened:
            transposed = ImageOps.exif_transpose(opened)
            try:
                logo = transposed.convert("RGBA")
                logo.load()
            finally:
                if transposed is not opened:
                    transposed.close()
        with logo.getchannel("A") as alpha:
            opaque = alpha.getextrema()[0] == 255
        if opaque:
            with logo.convert("L") as grayscale:
                with ImageChops.invert(grayscale) as inverted:
                    with inverted.point(
                        lambda value: min(255, int(value * 1.6))
                    ) as alpha_mask:
                        logo.putalpha(alpha_mask)
        with logo.getchannel("A") as alpha:
            alpha_bounds = alpha.getbbox()
        if logo.width <= 0 or logo.height <= 0 or alpha_bounds is None:
            raise ValueError("empty logo")
        cropped = logo.crop(alpha_bounds)
        logo.close()
        logo = cropped
        contained = ImageOps.contain(
            logo,
            (rect.width, rect.height),
            Image.Resampling.LANCZOS,
        )
        contained.load()
        x = rect.x + (rect.width - contained.width) // 2
        y = rect.y + (rect.height - contained.height) // 2
        with canvas.crop((x, y, x + contained.width, y + contained.height)) as crop:
            with crop.convert("RGB") as local_background:
                _enforce_logo_contrast(contained, local_background)
        return contained, ()
    except (OSError, SyntaxError, ValueError):
        return None, (CoverWarning("logo_ilegivel", _LOGO_UNREADABLE),)
    finally:
        if logo is not None:
            logo.close()


def render_identity(
    canvas: Image.Image,
    layout: CurveLayout,
    data: IdentityData,
    palette: tema.Paleta,
) -> tuple[CoverWarning, ...]:
    """Render available cover identity within geometry-owned safe regions."""
    draw = ImageDraw.Draw(canvas)
    scale = _scale_for(canvas)
    title = data.title.strip()
    studio = data.studio.strip()
    site = data.site.strip()
    lines = _identity_lines(draw, title, studio, layout.identity_safe_rect, scale)
    site_font_and_bounds = (
        _fit_font(draw, site, tema.SANS_MEDIO, _SITE_SIZES, layout.site_rect, scale)
        if site
        else None
    )
    logo, warnings = _prepare_logo(data.logo_path, layout.logo_rect, canvas)

    identity_colors = (
        ((palette.texto,) if title else ())
        + ((palette.apagado,) if studio else ())
    )
    fills = tuple(_rgb(color) for color in identity_colors)
    _draw_identity_lines(draw, layout.identity_safe_rect, lines, fills, scale)
    if site_font_and_bounds is not None:
        font, bounds = site_font_and_bounds
        _draw_centered(draw, layout.site_rect, site, font, bounds, _rgb(palette.acento))
    if logo is not None:
        try:
            x = layout.logo_rect.x + (layout.logo_rect.width - logo.width) // 2
            y = layout.logo_rect.y + (layout.logo_rect.height - logo.height) // 2
            canvas.paste(logo, (x, y), logo)
        finally:
            logo.close()
    return warnings
