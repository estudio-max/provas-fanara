from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from PIL import Image, ImageChops, ImageDraw

from provas import tema
from provas.capa_curvas import CurveLayout, PixelRect, layout_orbita, render_mask


def _changed_bbox(before: Image.Image, after: Image.Image) -> PixelRect | None:
    bbox = ImageChops.difference(before, after).getbbox()
    if bbox is None:
        return None
    return PixelRect(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])


def _color_bbox(image: Image.Image, color: tuple[int, int, int]) -> PixelRect | None:
    mask = Image.new("L", image.size, 0)
    mask.putdata([255 if pixel == color else 0 for pixel in image.get_flattened_data()])
    bbox = mask.getbbox()
    if bbox is None:
        return None
    return PixelRect(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])


def _contrast_ratio(
    foreground: tuple[int, int, int],
    background: tuple[int, int, int],
) -> float:
    def luminance(color: tuple[int, int, int]) -> float:
        channels = tuple(channel / 255 for channel in color)
        linear = tuple(
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        )
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    foreground_luminance = luminance(foreground)
    background_luminance = luminance(background)
    return (max(foreground_luminance, background_luminance) + 0.05) / (
        min(foreground_luminance, background_luminance) + 0.05
    )


def test_identity_records_are_immutable_and_overflow_is_a_value_error():
    from provas.identidade_capa import CoverTextOverflow, CoverWarning, IdentityData

    identity = IdentityData("Ensaio Aurora", "Fanara Fotografia", "fanara.example")
    warning = CoverWarning("logo_ausente", "Logotipo ausente")

    assert identity.logo_path == ""
    assert isinstance(CoverTextOverflow("não cabe"), ValueError)
    with pytest.raises(FrozenInstanceError):
        identity.title = "Outro"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        warning.code = "outro"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("data", "rect_name"),
    [
        (("Ensaio Aurora", "", ""), "identity_safe_rect"),
        (("", "Fanara Fotografia", ""), "identity_safe_rect"),
        (("", "", "fanara.example"), "site_rect"),
    ],
)
def test_each_text_field_is_deterministic_and_stays_inside_its_safe_rect(data, rect_name):
    from provas.identidade_capa import IdentityData, render_identity

    layout = layout_orbita(1600, 1131, 6)
    palette = tema.paleta()
    before = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
    first = before.copy()
    second = before.copy()

    first_warnings = render_identity(first, layout, IdentityData(*data), palette)
    second_warnings = render_identity(second, layout, IdentityData(*data), palette)

    changed = _changed_bbox(before, first)
    assert changed is not None
    safe_rect = getattr(layout, rect_name)
    assert changed.intersection(safe_rect) == changed
    assert first.tobytes() == second.tobytes()
    assert first_warnings == second_warnings == (
        pytest.importorskip("provas.identidade_capa").CoverWarning(
            "logo_ausente", "O logotipo não foi encontrado; a capa foi criada sem ele."
        ),
    )


def test_site_text_is_composed_over_background_without_photo_pixels():
    from provas.identidade_capa import IdentityData, render_identity

    size = (1600, 1131)
    palette = tema.paleta()
    layout = layout_orbita(*size, 9)
    canvas = Image.new("RGB", size, palette.fundo_rgb)
    photo_color = (255, 0, 255)
    photo = Image.new("RGB", size, photo_color)
    for slot in layout.slots:
        with render_mask(slot, size) as mask:
            canvas.paste(photo, (0, 0), mask)

    render_identity(canvas, layout, IdentityData("", "", "fanara.example"), palette)

    site = canvas.crop(
        (
            layout.site_rect.x,
            layout.site_rect.y,
            layout.site_rect.right,
            layout.site_rect.bottom,
        )
    )
    assert photo_color not in set(site.get_flattened_data())
    assert set(site.get_flattened_data()) != {palette.fundo_rgb}


def test_title_and_studio_have_distinct_balanced_lines_and_empty_optional_fields_are_omitted():
    from provas.identidade_capa import IdentityData, render_identity

    layout = layout_orbita(1600, 1131, 6)
    palette = replace(tema.paleta(), texto=(1.0, 0.0, 0.0), apagado=(0.0, 1.0, 0.0))
    background = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
    title_only = background.copy()
    studio_only = background.copy()
    combined = background.copy()
    title_with_empty_optionals = background.copy()

    render_identity(title_only, layout, IdentityData("Ensaio Aurora", "", ""), palette)
    render_identity(studio_only, layout, IdentityData("", "Fanara Fotografia", ""), palette)
    render_identity(
        combined,
        layout,
        IdentityData("Ensaio Aurora", "Fanara Fotografia", ""),
        palette,
    )
    render_identity(
        title_with_empty_optionals,
        layout,
        IdentityData("Ensaio Aurora", "  ", "\t"),
        palette,
    )

    title_color = tuple(round(channel * 255) for channel in palette.texto)
    studio_color = tuple(round(channel * 255) for channel in palette.apagado)
    title_bbox = _color_bbox(combined, title_color)
    studio_bbox = _color_bbox(combined, studio_color)
    assert title_bbox is not None and studio_bbox is not None
    assert title_bbox.intersection(studio_bbox).area == 0
    assert _changed_bbox(background, combined) is not None
    assert title_only.tobytes() == title_with_empty_optionals.tobytes()


def test_overflow_raises_exact_message_before_mutating_the_canvas():
    from provas.identidade_capa import CoverTextOverflow, IdentityData, render_identity

    palette = tema.paleta()
    canvas = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
    before = canvas.tobytes()
    layout = CurveLayout(
        (),
        PixelRect(700, 500, 2, 2),
        PixelRect(10, 10, 100, 50),
        PixelRect(1300, 1000, 100, 30),
    )

    with pytest.raises(
        CoverTextOverflow,
        match=r"^O texto da capa não cabe\. Abrevie o conteúdo antes de exportar\.$",
    ):
        render_identity(
            canvas,
            layout,
            IdentityData("Título", "Estúdio", "site.example"),
            palette,
        )

    assert canvas.tobytes() == before


@pytest.mark.parametrize("logo_path", ["", "arquivo-que-nao-existe.png"])
def test_absent_logo_is_non_blocking_and_returns_one_portuguese_warning(logo_path):
    from provas.identidade_capa import CoverWarning, IdentityData, render_identity

    palette = tema.paleta()
    canvas = Image.new("RGB", (1600, 1131), palette.fundo_rgb)

    warnings = render_identity(
        canvas,
        layout_orbita(1600, 1131, 6),
        IdentityData("", "", "", logo_path),
        palette,
    )

    assert warnings == (
        CoverWarning("logo_ausente", "O logotipo não foi encontrado; a capa foi criada sem ele."),
    )
    assert canvas.getbbox() is not None
    assert set(canvas.get_flattened_data()) == {palette.fundo_rgb}


def test_corrupt_logo_is_non_blocking_and_returns_one_legibility_warning(tmp_path):
    from provas.identidade_capa import CoverWarning, IdentityData, render_identity

    corrupt = tmp_path / "logo.png"
    corrupt.write_bytes(b"isto nao e uma imagem")
    palette = tema.paleta()
    canvas = Image.new("RGB", (1600, 1131), palette.fundo_rgb)

    warnings = render_identity(
        canvas,
        layout_orbita(1600, 1131, 6),
        IdentityData("", "", "", str(corrupt)),
        palette,
    )

    assert warnings == (
        CoverWarning("logo_ilegivel", "O logotipo não pôde ser lido; a capa foi criada sem ele."),
    )
    assert set(canvas.get_flattened_data()) == {palette.fundo_rgb}


@pytest.mark.parametrize("source_size", [(400, 100), (100, 400)])
def test_valid_horizontal_and_vertical_logos_are_contained_without_distortion(tmp_path, source_size):
    from provas.identidade_capa import IdentityData, render_identity

    path = tmp_path / f"logo-{source_size[0]}x{source_size[1]}.png"
    Image.new("RGBA", source_size, (0, 0, 0, 255)).save(path)
    palette = tema.paleta("#F7F4EF")
    background = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
    canvas = background.copy()
    layout = layout_orbita(1600, 1131, 6)

    warnings = render_identity(
        canvas,
        layout,
        IdentityData("", "", "", str(path)),
        palette,
    )

    changed = _changed_bbox(background, canvas)
    assert warnings == ()
    assert changed is not None
    assert changed.intersection(layout.logo_rect) == changed
    assert changed.width / changed.height == pytest.approx(source_size[0] / source_size[1], rel=0.04)
    path.unlink()  # Pillow must not retain an open file handle on Windows.


def test_alpha_logo_preserves_transparency_and_dark_palette_converts_black_for_contrast(tmp_path):
    from provas.identidade_capa import IdentityData, render_identity

    path = tmp_path / "logo-alpha.png"
    logo = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    ImageDraw.Draw(logo).ellipse((50, 25, 149, 74), fill=(0, 0, 0, 255))
    logo.save(path)
    logo.close()
    palette = tema.paleta("#16161A")
    canvas = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
    layout = layout_orbita(1600, 1131, 6)

    warnings = render_identity(
        canvas,
        layout,
        IdentityData("", "", "", str(path)),
        palette,
    )

    changed = _changed_bbox(Image.new("RGB", canvas.size, palette.fundo_rgb), canvas)
    assert warnings == ()
    assert changed is not None
    assert changed.width < layout.logo_rect.width
    assert changed.height <= layout.logo_rect.height
    assert canvas.getpixel((changed.x, changed.y)) == palette.fundo_rgb
    center = (changed.x + changed.width // 2, changed.y + changed.height // 2)
    assert canvas.getpixel(center) == (255, 255, 255)


@pytest.mark.parametrize(
    ("source_color", "background"),
    [
        ((255, 255, 255), "#F7F4EF"),
        ((0, 0, 0), "#16161A"),
        ((0, 0, 0), "#F7F4EF"),
        ((255, 255, 255), "#16161A"),
    ],
)
def test_logo_content_keeps_alpha_and_reaches_4_5_contrast(
    tmp_path,
    source_color,
    background,
):
    from provas.identidade_capa import IdentityData, render_identity

    path = tmp_path / f"logo-{source_color[0]}-{background[1:]}.png"
    logo = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    ImageDraw.Draw(logo).ellipse((50, 25, 149, 74), fill=(*source_color, 255))
    logo.save(path)
    logo.close()
    palette = tema.paleta(background)
    original = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
    canvas = original.copy()

    warnings = render_identity(
        canvas,
        layout_orbita(1600, 1131, 6),
        IdentityData("", "", "", str(path)),
        palette,
    )

    changed = _changed_bbox(original, canvas)
    assert warnings == ()
    assert changed is not None
    center = (changed.x + changed.width // 2, changed.y + changed.height // 2)
    rendered_color = canvas.getpixel(center)
    assert _contrast_ratio(rendered_color, palette.fundo_rgb) >= 4.5
    if _contrast_ratio(source_color, palette.fundo_rgb) >= 4.5:
        assert rendered_color == source_color
    assert canvas.getpixel((changed.x, changed.y)) == palette.fundo_rgb


@pytest.mark.parametrize(
    ("palette_background", "local_background", "source_color"),
    [
        ("#F7F4EF", (12, 12, 14), (255, 255, 255)),
        ("#16161A", (245, 245, 242), (0, 0, 0)),
    ],
)
def test_logo_contrast_is_measured_against_canvas_pixels_under_its_alpha(
    tmp_path,
    palette_background,
    local_background,
    source_color,
):
    from provas.identidade_capa import IdentityData, render_identity

    path = tmp_path / "logo-local.png"
    logo = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    ImageDraw.Draw(logo).ellipse((50, 25, 149, 74), fill=(*source_color, 255))
    logo.save(path)
    logo.close()
    palette = tema.paleta(palette_background)
    layout = layout_orbita(1600, 1131, 6)
    canvas = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
    ImageDraw.Draw(canvas).rectangle(
        (
            layout.logo_rect.x,
            layout.logo_rect.y,
            layout.logo_rect.right - 1,
            layout.logo_rect.bottom - 1,
        ),
        fill=local_background,
    )

    render_identity(canvas, layout, IdentityData("", "", "", str(path)), palette)

    center = (
        layout.logo_rect.x + layout.logo_rect.width // 2,
        layout.logo_rect.y + layout.logo_rect.height // 2,
    )
    rendered_color = canvas.getpixel(center)
    assert rendered_color == source_color
    assert _contrast_ratio(rendered_color, local_background) >= 4.5


@pytest.mark.parametrize(
    ("source_color", "majority_background", "minority_background"),
    [
        ((255, 255, 255), (0, 0, 0), (255, 255, 255)),
        ((0, 0, 0), (255, 255, 255), (0, 0, 0)),
    ],
)
def test_every_nontransparent_logo_pixel_has_contrast_on_heterogeneous_canvas(
    tmp_path,
    source_color,
    majority_background,
    minority_background,
):
    import provas.identidade_capa as identity

    layout = layout_orbita(1600, 1131, 6)
    rect = layout.logo_rect
    path = tmp_path / f"logo-adversarial-{source_color[0]}.png"
    source = Image.new("RGBA", (rect.width, rect.height), (*source_color, 255))
    source.putpixel((rect.width // 2, rect.height // 2), (*source_color, 0))
    source.save(path)
    source_alpha = tuple(source.getchannel("A").get_flattened_data())
    source.close()
    canvas = Image.new("RGB", (1600, 1131), (127, 127, 127))
    split = rect.x + round(rect.width * 0.9)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle(
        (rect.x, rect.y, split - 1, rect.bottom - 1),
        fill=majority_background,
    )
    draw.rectangle(
        (split, rect.y, rect.right - 1, rect.bottom - 1),
        fill=minority_background,
    )

    prepared, warnings = identity._prepare_logo(str(path), rect, canvas)

    assert warnings == ()
    assert prepared is not None
    try:
        background = canvas.crop((rect.x, rect.y, rect.right, rect.bottom))
        prepared_pixels = tuple(prepared.get_flattened_data())
        background_pixels = tuple(background.get_flattened_data())
        assert tuple(pixel[3] for pixel in prepared_pixels) == source_alpha
        assert all(
            _contrast_ratio(pixel[:3], background_pixel) >= 4.5
            for pixel, background_pixel in zip(prepared_pixels, background_pixels)
            if pixel[3]
        )
        for pixel, background_pixel in zip(prepared_pixels, background_pixels):
            if not pixel[3]:
                continue
            if _contrast_ratio(source_color, background_pixel) >= 4.5:
                assert pixel[:3] == source_color
            else:
                assert pixel[:3] != source_color
    finally:
        prepared.close()


def test_opaque_white_logo_background_uses_the_existing_cutout_behavior(tmp_path):
    from provas.identidade_capa import IdentityData, render_identity

    path = tmp_path / "logo-fundo-branco.png"
    logo = Image.new("RGB", (200, 100), (255, 255, 255))
    ImageDraw.Draw(logo).rectangle((50, 25, 149, 74), fill=(0, 0, 0))
    logo.save(path)
    logo.close()
    palette = tema.paleta("#F7F4EF")
    background = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
    canvas = background.copy()
    layout = layout_orbita(1600, 1131, 6)

    render_identity(canvas, layout, IdentityData("", "", "", str(path)), palette)

    changed = _changed_bbox(background, canvas)
    assert changed is not None
    assert canvas.getpixel((changed.x, changed.y)) == (0, 0, 0)


@pytest.mark.parametrize(
    ("field", "sizes", "font_name", "color_name"),
    [
        ("title", tuple(range(54, 31, -2)), "SERIF", "texto"),
        ("studio", tuple(range(26, 17, -1)), "SANS_MEDIO", "apagado"),
        ("site", tuple(range(18, 13, -1)), "SANS_MEDIO", "acento"),
    ],
)
def test_every_exact_design_font_fit_boundary(field, sizes, font_name, color_name):
    import provas.identidade_capa as identity

    palette = tema.paleta()
    source = getattr(tema, font_name)
    text = "MMMMMMMM"
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for target_size in sizes:
        target_font = identity._font(source, target_size)
        target_bounds = probe.textbbox((0, 0), text, font=target_font)
        rect = PixelRect(
            500,
            450,
            target_bounds[2] - target_bounds[0],
            target_bounds[3] - target_bounds[1],
        )
        identity_rect = rect if field != "site" else PixelRect(600, 400, 300, 200)
        site_rect = rect if field == "site" else PixelRect(1300, 1000, 200, 50)
        layout = CurveLayout((), identity_rect, PixelRect(10, 10, 100, 40), site_rect)
        values = {"title": "", "studio": "", "site": ""}
        values[field] = text
        actual = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
        expected = actual.copy()

        identity.render_identity(actual, layout, identity.IdentityData(**values), palette)
        expected_draw = ImageDraw.Draw(expected)
        identity._draw_centered(
            expected_draw,
            rect,
            text,
            target_font,
            target_bounds,
            identity._rgb(getattr(palette, color_name)),
        )

        assert actual.tobytes() == expected.tobytes(), (field, target_size)


@pytest.mark.parametrize("background", ["#16161A", "#F7F4EF"])
def test_text_uses_palette_contrast_on_light_and_dark_backgrounds(background):
    from provas.identidade_capa import IdentityData, render_identity

    palette = tema.paleta(background)
    canvas = Image.new("RGB", (1600, 1131), palette.fundo_rgb)

    render_identity(
        canvas,
        layout_orbita(1600, 1131, 6),
        IdentityData("Título", "Estúdio", "site.example"),
        palette,
    )

    pixels = set(canvas.get_flattened_data())
    assert tuple(round(channel * 255) for channel in palette.texto) in pixels
    assert tuple(round(channel * 255) for channel in palette.apagado) in pixels
    assert tuple(round(channel * 255) for channel in palette.acento) in pixels


def test_exif_oriented_logo_and_all_identity_fields_render_together(tmp_path):
    from provas.identidade_capa import IdentityData, render_identity

    path = tmp_path / "logo-orientado.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (400, 100), (0, 0, 0)).save(path, exif=exif)
    palette = tema.paleta("#F7F4EF")
    background = Image.new("RGB", (1600, 1131), palette.fundo_rgb)
    canvas = background.copy()
    layout = layout_orbita(1600, 1131, 6)

    warnings = render_identity(
        canvas,
        layout,
        IdentityData("Ensaio Aurora", "Fanara Fotografia", "fanara.example", str(path)),
        palette,
    )

    assert warnings == ()
    logo_changed = _changed_bbox(
        background.crop((layout.logo_rect.x, layout.logo_rect.y, layout.logo_rect.right, layout.logo_rect.bottom)),
        canvas.crop((layout.logo_rect.x, layout.logo_rect.y, layout.logo_rect.right, layout.logo_rect.bottom)),
    )
    assert logo_changed is not None
    assert logo_changed.height > logo_changed.width
    canvas.getpixel((0, 0))  # Rendering leaves the caller-owned image open and usable.
