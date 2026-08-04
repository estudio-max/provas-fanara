from __future__ import annotations

from PIL import Image

from provas import tema


def test_editorial_mosaic_renders_title_safe_colored_cover():
    from provas.capas import gerar_mosaico_editorial

    colors = (
        (235, 48, 48), (48, 190, 65), (45, 100, 235),
        (230, 200, 45), (210, 55, 180), (40, 205, 195),
        (242, 130, 40), (130, 70, 215), (85, 170, 90),
    )
    items = [Image.new("RGB", (180 + index * 3, 120 + index * 2), color) for index, color in enumerate(colors)]
    palette = tema.paleta("#16161A")

    cover = gerar_mosaico_editorial(items, 1600, 1131, palette)

    assert cover.imagem.size == (1600, 1131)
    assert 0.60 <= cover.ancora <= 0.85
    safe_y = int(cover.imagem.height * (cover.ancora + 0.05))
    assert cover.imagem.getpixel((cover.imagem.width // 2, safe_y)) == palette.fundo_rgb
    pixels = list(cover.imagem.get_flattened_data())
    assert all(color in pixels for color in colors)


def test_gerar_uses_editorial_mosaic_as_the_default_style():
    from provas.capas import gerar

    items = [Image.new("RGB", (80, 120), (200, 20, 20)), Image.new("RGB", (120, 80), (20, 200, 20))]
    palette = tema.paleta()

    generated = gerar("mosaico", items, 320, 226, palette)
    fallback = gerar("unknown", items, 320, 226, palette)

    assert generated == fallback
    assert generated.ancora >= 0.60
