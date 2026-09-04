from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from provas.modelos import BookPlan, PagePlan, PhotoInfo, Rect
from provas.templates import catalog, fit_contain


def _photo(path: Path, index: int) -> PhotoInfo:
    with Image.open(path) as image:
        width, height = image.size
    return PhotoInfo(str(path), str(path), path.name, width, height, index)


def _point_rect(rect, page_width: float, page_height: float) -> pymupdf.Rect:
    return pymupdf.Rect(
        rect.x * page_width,
        rect.y * page_height,
        rect.right * page_width,
        rect.bottom * page_height,
    )


@pytest.mark.parametrize(
    ("background", "expected_rgb"),
    (("branco", (255, 255, 255)), ("cinza", (210, 210, 210)), ("preto", (17, 18, 21))),
)
@pytest.mark.parametrize("shadow", (False, True))
@pytest.mark.parametrize("mode", ("prova", "fotolivro"))
def test_page_background_and_photo_shadow_preserve_photos_and_slots(
    tmp_path: Path,
    image_factory,
    background: str,
    expected_rgb: tuple[int, int, int],
    shadow: bool,
    mode: str,
):
    """Every internal-page preset is exact and shadow layers stay inside their slots."""
    from provas import tema
    from provas.documento import Documento, Tipografia

    paths = (
        image_factory("shadow-portrait.jpg", size=(200, 300), color=(220, 40, 40)),
        image_factory("shadow-landscape.jpg", size=(300, 200), color=(40, 80, 220)),
    )
    infos = tuple(_photo(path, index) for index, path in enumerate(paths))
    page_plan = PagePlan(1, "pair-asymmetric-left", tuple(info.id for info in infos), "opening")
    template = next(item for item in catalog() if item.id == page_plan.template_id).resolve(mode)
    document = Documento(
        "Ensaio", "", True, Tipografia(), None,
        paleta=tema.paleta_paginas(background), sombra_fotos=shadow, modo=mode,
    )
    document.render_page(page_plan, template, {info.id: info for info in infos})
    output = tmp_path / f"{background}-{shadow}-{mode}.pdf"
    document.salvar(str(output))
    document.fechar()
    baseline = Documento(
        "Ensaio", "", True, Tipografia(), None,
        paleta=tema.paleta_paginas(background), sombra_fotos=False, modo=mode,
    )
    baseline.render_page(page_plan, template, {info.id: info for info in infos})
    baseline_output = tmp_path / f"{background}-baseline-{mode}.pdf"
    baseline.salvar(str(baseline_output))
    baseline.fechar()

    with pymupdf.open(output) as pdf, pymupdf.open(baseline_output) as baseline_pdf:
        page = pdf[0]
        baseline_page = baseline_pdf[0]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False)
        try:
            rendered = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            for point in ((2, 2), (pixmap.width - 3, 2), (2, pixmap.height - 3)):
                assert rendered.getpixel(point) == expected_rgb
        finally:
            rendered.close()

        images = page.get_images(full=True)
        baseline_images = baseline_page.get_images(full=True)
        assert len(images) == len(infos)
        assert len(baseline_images) == len(images)
        for image, baseline_image, info, slot in zip(images, baseline_images, infos, template.slots):
            assert pdf.extract_image(image[0])["image"] == baseline_pdf.extract_image(baseline_image[0])["image"]
            image_rect = page.get_image_rects(image)[0]
            baseline_rect = baseline_page.get_image_rects(baseline_image)[0]
            assert tuple(image_rect) == pytest.approx(tuple(baseline_rect), abs=0.01)
            bounds = _point_rect(slot.rect, page.rect.width, page.rect.height)
            expected = fit_contain(Rect(bounds.x0, bounds.y0, bounds.width, bounds.height), info.width / info.height)
            assert tuple(image_rect) == pytest.approx(
                (expected.x, expected.y, expected.right, expected.bottom), abs=0.05,
            )

        fills = [drawing for drawing in page.get_drawings() if drawing.get("fill") == (0.0, 0.0, 0.0)]
        assert len(fills) == (3 * len(infos) if shadow else 0)
        if shadow:
            assert sum(drawing["fill_opacity"] for drawing in fills) / len(infos) == pytest.approx(0.145)
            assert sum(drawing["fill_opacity"] for drawing in fills) / len(infos) < 0.16
        for drawing in fills:
            assert any(drawing["fill_opacity"] == pytest.approx(opacity, abs=1e-6)
                       for opacity in (0.075, 0.045, 0.025))
            containing_slots = [
                _point_rect(slot.rect, page.rect.width, page.rect.height)
                for slot in template.slots
                if (
                    drawing["rect"].x0 >= _point_rect(slot.rect, page.rect.width, page.rect.height).x0 - 0.05
                    and drawing["rect"].y0 >= _point_rect(slot.rect, page.rect.width, page.rect.height).y0 - 0.05
                    and drawing["rect"].x1 <= _point_rect(slot.rect, page.rect.width, page.rect.height).x1 + 0.05
                    and drawing["rect"].y1 <= _point_rect(slot.rect, page.rect.width, page.rect.height).y1 + 0.05
                )
            ]
            assert containing_slots
            assert not any(
                _point_rect(other.rect, page.rect.width, page.rect.height).intersects(drawing["rect"])
                for other in template.slots
                if other.rect not in {
                    slot.rect for slot in template.slots
                    if _point_rect(slot.rect, page.rect.width, page.rect.height) in containing_slots
                }
            )


@pytest.mark.parametrize(
    ("template_id", "sizes"),
    [
        ("single-portrait", ((200, 300),)),
        ("single-landscape", ((300, 200),)),
        ("pair-asymmetric-left", ((200, 300), (300, 200))),
        ("quad-grid", ((200, 300), (300, 200), (200, 300), (300, 200))),
    ],
)
@pytest.mark.parametrize("mode", ["prova", "fotolivro"])
def test_render_page_uses_a4_landscape_slots_without_cropping(
    tmp_path: Path, image_factory, template_id: str, sizes: tuple[tuple[int, int], ...], mode: str
):
    from provas.documento import Documento, Tipografia

    paths = [
        image_factory(f"arquivo_extremamente_longo_{index:02d}.jpg", size=size, color=(40 + index * 30, 80, 160))
        for index, size in enumerate(sizes)
    ]
    infos = tuple(_photo(path, index) for index, path in enumerate(paths))
    page_plan = PagePlan(1, template_id, tuple(info.id for info in infos), "opening")
    template = next(item for item in catalog() if item.id == template_id).resolve(mode)
    doc = Documento("Ensaio", "03.08.2026", True, Tipografia(), None, modo=mode)

    doc.render_page(page_plan, template, {info.id: info for info in infos})
    output = tmp_path / f"{mode}-{template_id}.pdf"
    doc.salvar(str(output))

    with pymupdf.open(output) as pdf:
        assert pdf.page_count == 1
        expected_title = "Ensaio — provas" if mode == "prova" else "Ensaio — fotolivro"
        assert pdf.metadata["title"] == expected_title
        page = pdf[0]
        assert page.rect.width == pytest.approx(841.89, abs=0.1)
        assert page.rect.height == pytest.approx(595.28, abs=0.1)
        assert len(page.get_images(full=True)) == len(infos)

        text = page.get_text()
        for info in infos:
            assert (info.label in text) is (mode == "prova")

        actual_rects = [page.get_image_rects(image)[0] for image in page.get_images(full=True)]
        extracted_colours = []
        for image_entry in page.get_images(full=True):
            extracted = pdf.extract_image(image_entry[0])["image"]
            with Image.open(io.BytesIO(extracted)) as embedded:
                extracted_colours.append(embedded.convert("RGB").getpixel((embedded.width // 2, embedded.height // 2)))
        expected_colours = [(40 + index * 30, 80, 160) for index in range(len(infos))]
        assert len(extracted_colours) == len(expected_colours)
        for actual_colour, expected_colour in zip(extracted_colours, expected_colours):
            assert actual_colour == pytest.approx(expected_colour, abs=2)

        for actual, info, slot in zip(actual_rects, infos, template.slots):
            slot_rect = _point_rect(slot.rect, page.rect.width, page.rect.height)
            assert actual.x0 >= slot_rect.x0 - 0.05
            assert actual.y0 >= slot_rect.y0 - 0.05
            assert actual.x1 <= slot_rect.x1 + 0.05
            assert actual.y1 <= slot_rect.y1 + 0.05
            physical = Rect(slot_rect.x0, slot_rect.y0, slot_rect.width, slot_rect.height)
            expected = fit_contain(physical, info.width / info.height)
            expected_rect = pymupdf.Rect(expected.x, expected.y, expected.right, expected.bottom)
            assert tuple(actual) == pytest.approx(tuple(expected_rect), abs=0.05)
            assert actual.width / actual.height == pytest.approx(info.width / info.height, rel=1e-4)


def test_proof_caption_is_ellipsized_inside_its_own_rectangle(tmp_path: Path, image_factory):
    from provas.documento import Documento, Tipografia

    path = image_factory(("nome_muito_longo_" * 8) + ".jpg", size=(200, 300))
    info = _photo(path, 0)
    page_plan = PagePlan(1, "single-portrait", (info.id,), "opening")
    template = next(item for item in catalog() if item.id == "single-portrait").resolve("prova")
    doc = Documento("Ensaio", "", True, Tipografia(), None, modo="prova")
    doc.render_page(page_plan, template, {info.id: info})
    output = tmp_path / "caption.pdf"
    doc.salvar(str(output))

    with pymupdf.open(output) as pdf:
        words = pdf[0].get_text("words")
        caption = _point_rect(template.slots[0].caption, pdf[0].rect.width, pdf[0].rect.height)
        caption_words = [word for word in words if pymupdf.Rect(word[:4]).intersects(caption)]
        assert caption_words
        assert all(caption.contains(pymupdf.Rect(word[:4])) for word in caption_words)
        assert info.label not in pdf[0].get_text()


def test_proof_caption_is_centered_on_each_photo_without_a_filled_band(tmp_path: Path, image_factory):
    from provas.documento import Documento, Tipografia

    paths = (
        image_factory("retrato.jpg", size=(200, 300), color=(220, 40, 40)),
        image_factory("paisagem.jpg", size=(300, 200), color=(40, 80, 220)),
    )
    infos = tuple(_photo(path, index) for index, path in enumerate(paths))
    page_plan = PagePlan(1, "pair-asymmetric-left", tuple(info.id for info in infos), "opening")
    template = next(item for item in catalog() if item.id == "pair-asymmetric-left").resolve("prova")
    doc = Documento("Ensaio", "", True, Tipografia(), None, modo="prova")
    doc.render_page(page_plan, template, {info.id: info for info in infos})
    output = tmp_path / "captions.pdf"
    doc.salvar(str(output))

    with pymupdf.open(output) as pdf:
        page = pdf[0]
        image_rects = [page.get_image_rects(image)[0] for image in page.get_images(full=True)]
        for image_rect, slot in zip(image_rects, template.slots):
            caption_rect = _point_rect(slot.caption, page.rect.width, page.rect.height)
            caption_words = [
                word for word in page.get_text("words") if pymupdf.Rect(word[:4]).intersects(caption_rect)
            ]

            assert caption_words
            assert not any(
                drawing.get("fill") is not None
                and drawing["rect"] != page.rect
                and drawing["rect"].intersects(caption_rect)
                for drawing in page.get_drawings()
            )
            word_rect = pymupdf.Rect(*caption_words[0][:4])
            assert (word_rect.x0 + word_rect.x1) / 2 == pytest.approx(
                (image_rect.x0 + image_rect.x1) / 2, abs=0.75
            )


def test_proof_caption_is_centered_on_each_physical_photo(tmp_path: Path, image_factory):
    from provas.documento import Documento, Tipografia

    paths = (
        image_factory("retrato.jpg", size=(200, 300), color=(220, 40, 40)),
        image_factory("paisagem.jpg", size=(300, 200), color=(40, 80, 220)),
    )
    infos = tuple(_photo(path, index) for index, path in enumerate(paths))
    page_plan = PagePlan(1, "pair-asymmetric-left", tuple(info.id for info in infos), "opening")
    template = next(item for item in catalog() if item.id == "pair-asymmetric-left").resolve("prova")
    doc = Documento("Ensaio", "", True, Tipografia(), None, modo="prova")
    doc.render_page(page_plan, template, {info.id: info for info in infos})
    output = tmp_path / "caption-centering.pdf"
    doc.salvar(str(output))

    with pymupdf.open(output) as pdf:
        page = pdf[0]
        image_rects = [page.get_image_rects(image)[0] for image in page.get_images(full=True)]
        for image_rect, slot in zip(image_rects, template.slots):
            caption_rect = _point_rect(slot.caption, page.rect.width, page.rect.height)
            caption_words = [
                word for word in page.get_text("words") if pymupdf.Rect(word[:4]).intersects(caption_rect)
            ]

            assert caption_words
            word_rect = pymupdf.Rect(*caption_words[0][:4])
            assert (word_rect.x0 + word_rect.x1) / 2 == pytest.approx(
                (image_rect.x0 + image_rect.x1) / 2, abs=0.75
            )


def test_proof_caption_keeps_an_identifiable_filename_prefix_inside_a_narrow_photo(
    tmp_path: Path, image_factory,
):
    """Adaptive typography precedes ellipsis when a portrait sits in a wide slot."""
    from provas.documento import Documento, Tipografia

    target = image_factory("FANARA_0003_PLANO_AMPLO.jpg", size=(200, 300), color=(220, 40, 40))
    companions = tuple(
        image_factory(f"companheira-{index}.jpg", size=(200, 300), color=(40, 80 + index * 20, 220))
        for index in range(3)
    )
    infos = tuple(_photo(path, index) for index, path in enumerate((companions[0], target, *companions[1:])))
    page_plan = PagePlan(1, "quad-left-feature", tuple(info.id for info in infos), "opening")
    template = next(item for item in catalog() if item.id == page_plan.template_id).resolve("prova")
    doc = Documento("Ensaio", "", True, Tipografia(), None, modo="prova")
    doc.render_page(page_plan, template, {info.id: info for info in infos})
    output = tmp_path / "caption-prefix.pdf"
    doc.salvar(str(output))

    with pymupdf.open(output) as pdf:
        page = pdf[0]
        image_rect = page.get_image_rects(page.get_images(full=True)[1])[0]
        caption = _point_rect(template.slots[1].caption, page.rect.width, page.rect.height)
        words = [word for word in page.get_text("words") if pymupdf.Rect(word[:4]).intersects(caption)]
        assert "FANARA_0003_PLANO_" in page.get_text()
        assert words
        word_rect = pymupdf.Rect(*words[0][:4])
        assert caption.contains(word_rect)
        assert (word_rect.x0 + word_rect.x1) / 2 == pytest.approx(
            (image_rect.x0 + image_rect.x1) / 2, abs=0.75
        )


def test_legacy_proof_caption_is_centered_on_its_photo_without_a_filled_band(tmp_path: Path, image_factory):
    from provas.documento import Documento, Tipografia

    path = image_factory("legado.jpg", size=(200, 300), color=(220, 40, 40))
    info = _photo(path, 0)
    doc = Documento("Ensaio", "", True, Tipografia(), None, modo="prova")
    page = doc.nova_pagina()
    cell = pymupdf.Rect(100, 80, 340, 420)
    doc.cartao(page, cell, path.read_bytes(), info.width / info.height, info.label, 20)
    output = tmp_path / "legacy-caption.pdf"
    doc.salvar(str(output))

    with pymupdf.open(output) as pdf:
        page = pdf[0]
        image_rect = page.get_image_rects(page.get_images(full=True)[0])[0]
        caption_rect = pymupdf.Rect(image_rect.x0, image_rect.y1, image_rect.x1, cell.y1)
        caption_words = [
            word for word in page.get_text("words") if pymupdf.Rect(word[:4]).intersects(caption_rect)
        ]

        assert caption_words
        assert not any(
            drawing.get("fill") is not None
            and drawing["rect"] != page.rect
            and drawing["rect"].intersects(caption_rect)
            for drawing in page.get_drawings()
        )
        word_rect = pymupdf.Rect(*caption_words[0][:4])
        assert (word_rect.x0 + word_rect.x1) / 2 == pytest.approx(
            (image_rect.x0 + image_rect.x1) / 2, abs=0.75
        )


def test_legacy_card_shadow_is_vector_clipped_and_preserves_its_jpeg(tmp_path: Path, image_factory):
    from provas import tema
    from provas.documento import Documento, Tipografia

    path = image_factory("legacy-shadow.jpg", size=(200, 300), color=(220, 40, 40))
    info = _photo(path, 0)
    cell = pymupdf.Rect(100, 80, 340, 420)
    documents = []
    for shadow in (False, True):
        document = Documento(
            "Ensaio", "", True, Tipografia(), None,
            paleta=tema.paleta_paginas("preto"), sombra_fotos=shadow, modo="prova",
        )
        page = document.nova_pagina()
        document.cartao(page, cell, path.read_bytes(), info.width / info.height, info.label, 20)
        output = tmp_path / f"legacy-shadow-{shadow}.pdf"
        document.salvar(str(output))
        document.fechar()
        documents.append(output)

    with pymupdf.open(documents[0]) as plain_pdf, pymupdf.open(documents[1]) as shadow_pdf:
        plain_page, shadow_page = plain_pdf[0], shadow_pdf[0]
        plain_image = plain_page.get_images(full=True)[0]
        shadow_image = shadow_page.get_images(full=True)[0]
        assert plain_pdf.extract_image(plain_image[0])["image"] == shadow_pdf.extract_image(shadow_image[0])["image"]
        assert tuple(plain_page.get_image_rects(plain_image)[0]) == pytest.approx(
            tuple(shadow_page.get_image_rects(shadow_image)[0]), abs=0.01,
        )
        shadows = [drawing for drawing in shadow_page.get_drawings() if drawing.get("fill") == (0.0, 0.0, 0.0)]
        assert len(shadows) == 3
        safe_bounds = pymupdf.Rect(
            cell.x0 + tema.RESPIRO_CARTAO,
            cell.y0 + tema.RESPIRO_CARTAO,
            cell.x1 - tema.RESPIRO_CARTAO,
            cell.y1 - 20,
        )
        assert all(
            drawing["rect"].x0 >= safe_bounds.x0 - 0.05
            and drawing["rect"].y0 >= safe_bounds.y0 - 0.05
            and drawing["rect"].x1 <= safe_bounds.x1 + 0.05
            and drawing["rect"].y1 <= safe_bounds.y1 + 0.05
            for drawing in shadows
        )


def test_thumbnail_reuses_pdf_rendering_rules_and_cache(image_factory):
    from provas import preview

    path = image_factory("vertical.jpg", size=(200, 300), color=(220, 40, 40))
    info = _photo(path, 0)
    plan = BookPlan(91, "prova", (), (PagePlan(1, "single-portrait", (info.id,), "opening"),))
    assets = {info.id: info}

    first = preview.render_page_thumbnail(plan, 1, assets, 420)
    second = preview.render_page_thumbnail(plan, 1, assets, 420)

    assert first is second
    assert first.size == (420, pytest.approx(420 / (297 / 210), abs=1))


def test_thumbnail_cache_fingerprints_asset_content_and_is_lru_bounded(image_factory, monkeypatch):
    from provas import preview
    from provas.documento import RenderAsset

    preview.clear_cache()
    monkeypatch.setattr(preview, "_CACHE_LIMIT", 2)
    path = image_factory("vertical.jpg", size=(200, 300))
    info = _photo(path, 0)
    plan = BookPlan(91, "prova", (), (PagePlan(1, "single-portrait", (info.id,), "opening"),))

    def asset(color):
        image = Image.new("RGB", (200, 300), color)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return {info.id: RenderAsset(info.id, info.label, buffer.getvalue(), 200, 300)}

    red = preview.render_page_thumbnail(plan, 1, asset((220, 20, 20)), 300)
    blue = preview.render_page_thumbnail(plan, 1, asset((20, 20, 220)), 300)
    preview.render_page_thumbnail(plan, 1, asset((20, 220, 20)), 301)
    red_again = preview.render_page_thumbnail(plan, 1, asset((220, 20, 20)), 300)

    assert red.tobytes() != blue.tobytes()
    assert red_again is not red
    assert len(preview._CACHE) == 2


def test_render_asset_keeps_jpeg_stream_for_pdf_embedding(image_factory):
    from provas.documento import RenderAsset

    path = image_factory("stream.jpg", size=(200, 300))
    data = path.read_bytes()
    asset = RenderAsset("photo", "stream.jpg", data, 200, 300)

    with Image.open(io.BytesIO(asset.jpeg)) as image:
        assert image.format == "JPEG"
        assert asset.ratio == pytest.approx(2 / 3)
