from __future__ import annotations

import pytest
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


def test_gerar_dispatches_mosaic_explicitly_and_rejects_unknown_style():
    from provas.capas import gerar

    items = [Image.new("RGB", (80, 120), (200, 20, 20)), Image.new("RGB", (120, 80), (20, 200, 20))]
    palette = tema.paleta()

    generated = gerar("mosaico", items, 320, 226, palette)

    assert generated.ancora >= 0.60
    with pytest.raises(ValueError, match="Estilo de capa inválido"):
        gerar("unknown", items, 320, 226, palette)


def test_gerar_dispatches_curved_cover_with_identity_and_seed(monkeypatch):
    from provas import capas
    from provas.identidade_capa import IdentityData

    image = Image.new("RGB", (80, 120), (20, 80, 140))
    items = [capas.CoverPhoto("photo", image)]
    identity = IdentityData("Ensaio", "Estúdio", "site.example")
    expected = capas.Capa(Image.new("RGB", (16, 11)), 0.34, identity_embedded=True)
    observed = []

    def curved(photos, width, height, palette, supplied_identity, seed):
        observed.append((photos, width, height, palette, supplied_identity, seed))
        return expected

    monkeypatch.setattr(capas, "gerar_curvas_editoriais", curved)

    actual = capas.gerar(
        "curvas_editoriais", items, 320, 226, tema.paleta(), identity=identity, seed=37
    )

    assert actual is expected
    assert observed == [(items, 320, 226, tema.paleta(), identity, 37)]
    expected.imagem.close()
    image.close()


def test_legacy_cover_constructor_remains_valid_with_identity_metadata_defaults():
    from provas.capas import Capa

    image = Image.new("RGB", (16, 11), (20, 20, 20))

    cover = Capa(image, 0.72)

    assert cover.imagem is image
    assert cover.ancora == 0.72
    assert cover.identity_embedded is False
    assert cover.warnings == ()
    assert cover.used_photo_ids == ()
