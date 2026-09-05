from __future__ import annotations

from dataclasses import FrozenInstanceError
import io

import pymupdf
import pytest
from PIL import Image

from provas import tema
from provas.enquadramento import CropRect, FrameResult
from provas.identidade_capa import IdentityData


def _safe_frame(image, target_size, preferred_focus):
    return FrameResult(
        image.resize(target_size),
        CropRect(0.0, 0.0, 1.0, 1.0),
        (),
        0,
        True,
    )


def _unsafe_frame(image, target_size, preferred_focus):
    result = _safe_frame(image, target_size, preferred_focus)
    return FrameResult(result.image, result.crop, result.face_boxes, 0, False)


def test_cover_photo_keeps_id_and_caller_owned_image_immutably():
    from provas.capas import CoverPhoto

    image = Image.new("RGB", (80, 120), (20, 40, 60))
    photo = CoverPhoto("portrait-a", image)

    assert photo.id == "portrait-a"
    assert photo.image is image
    with pytest.raises(FrozenInstanceError):
        photo.id = "replacement"  # type: ignore[misc]
    assert image.getpixel((0, 0)) == (20, 40, 60)
    image.close()


def test_curved_cover_rejects_repeated_photo_ids_before_rendering(monkeypatch):
    from provas import capas

    first = Image.new("RGB", (100, 140), (20, 40, 60))
    second = Image.new("RGB", (100, 140), (60, 40, 20))
    monkeypatch.setattr(capas, "frame_for_mask", _unsafe_frame)

    with pytest.raises(ValueError, match="identificadores únicos"):
        capas.gerar_curvas_editoriais(
            [capas.CoverPhoto("duplicate", first), capas.CoverPhoto("duplicate", second)],
            320,
            226,
            tema.paleta(),
            IdentityData("Ensaio", "Estúdio", "site.example"),
            seed=3,
        )

    assert first.getpixel((0, 0)) == (20, 40, 60)
    assert second.getpixel((0, 0)) == (60, 40, 20)
    first.close()
    second.close()


@pytest.mark.parametrize("count", range(1, 10))
def test_curved_cover_uses_matching_layout_and_every_photo_once(
    count: int, monkeypatch
):
    from provas import capas

    originals = [
        Image.new("RGB", (100, 140), (20 * index, 80, 160))
        for index in range(1, count + 1)
    ]
    photos = [capas.CoverPhoto(f"photo-{index}", image) for index, image in enumerate(originals)]
    real_layout = capas.layout_orbita
    layout_counts: list[int] = []

    def observed_layout(width, height, supplied_count):
        layout_counts.append(supplied_count)
        return real_layout(width, height, supplied_count)

    monkeypatch.setattr(capas, "layout_orbita", observed_layout)
    monkeypatch.setattr(capas, "frame_for_mask", _safe_frame)

    cover = capas.gerar_curvas_editoriais(
        photos,
        320,
        226,
        tema.paleta(),
        IdentityData("Ensaio", "Estúdio", "site.example"),
        seed=42,
    )

    assert layout_counts == [count]
    assert cover.imagem.size == (320, 226)
    assert cover.identity_embedded is True
    assert cover.used_photo_ids == tuple(photo.id for photo in photos)
    assert len(set(cover.used_photo_ids)) == count
    assert all(image.getpixel((0, 0)) for image in originals)
    cover.imagem.close()
    for image in originals:
        image.close()


def test_automatic_association_prefers_safe_candidate_for_each_slot(monkeypatch):
    from provas import capas

    red = Image.new("RGB", (100, 140), (220, 20, 20))
    green = Image.new("RGB", (100, 140), (20, 220, 20))

    def slot_sensitive_frame(image, target_size, preferred_focus):
        safe = (
            image.getpixel((0, 0)) == (20, 220, 20) and preferred_focus[0] < 0.5
        ) or (
            image.getpixel((0, 0)) == (220, 20, 20) and preferred_focus[0] > 0.5
        )
        return FrameResult(
            image.resize(target_size), CropRect(0.0, 0.0, 1.0, 1.0), (), 0, safe
        )

    monkeypatch.setattr(capas, "frame_for_mask", slot_sensitive_frame)
    cover = capas.gerar_curvas_editoriais(
        [capas.CoverPhoto("red", red), capas.CoverPhoto("green", green)],
        320,
        226,
        tema.paleta(),
        IdentityData("Ensaio", "Estúdio", "site.example"),
        seed=7,
    )

    assert cover.used_photo_ids == ("green", "red")
    assert all(warning.code != "rosto_em_area_de_risco" for warning in cover.warnings)
    cover.imagem.close()
    red.close()
    green.close()


def test_automatic_association_uses_best_fallback_once_and_warns_in_portuguese(
    monkeypatch,
):
    from provas import capas

    source = Image.new("RGB", (140, 100), (20, 60, 180))

    def unsafe_frame(image, target_size, preferred_focus):
        return FrameResult(
            image.resize(target_size), CropRect(0.0, 0.0, 1.0, 1.0), (), 0, False
        )

    monkeypatch.setattr(capas, "frame_for_mask", unsafe_frame)
    cover = capas.gerar_curvas_editoriais(
        [capas.CoverPhoto("unsafe", source)],
        320,
        226,
        tema.paleta(),
        IdentityData("Ensaio", "Estúdio", "site.example"),
        seed=11,
    )

    warnings = [warning for warning in cover.warnings if warning.code == "rosto_em_area_de_risco"]
    assert cover.used_photo_ids == ("unsafe",)
    assert len(warnings) == 1
    assert "rosto" in warnings[0].message.lower()
    cover.imagem.close()
    assert source.getpixel((0, 0)) == (20, 60, 180)
    source.close()


def test_automatic_association_scores_slot_orientation(monkeypatch):
    from provas import capas

    landscape = Image.new("RGB", (180, 100), (180, 40, 40))
    portrait = Image.new("RGB", (100, 180), (40, 180, 40))
    monkeypatch.setattr(capas, "frame_for_mask", _safe_frame)

    cover = capas.gerar_curvas_editoriais(
        [capas.CoverPhoto("landscape", landscape), capas.CoverPhoto("portrait", portrait)],
        320,
        226,
        tema.paleta(),
        IdentityData("Ensaio", "Estúdio", "site.example"),
        seed=13,
    )

    assert cover.used_photo_ids == ("portrait", "landscape")
    cover.imagem.close()
    landscape.close()
    portrait.close()


def test_automatic_association_uses_quality_and_similarity_metadata(monkeypatch):
    from provas import capas

    photos = []
    for identifier, quality, group, color in (
        ("strong-a", 1.0, 1, (200, 40, 40)),
        ("similar-a", 0.9, 1, (160, 40, 40)),
        ("different-b", 0.6, 2, (40, 40, 200)),
    ):
        image = Image.new("RGB", (100, 180), color)
        image.info.update(
            quality=quality,
            sharpness=quality,
            exposure=quality,
            density=quality,
            similarity_group=group,
        )
        photos.append(capas.CoverPhoto(identifier, image))
    monkeypatch.setattr(capas, "frame_for_mask", _safe_frame)

    cover = capas.gerar_curvas_editoriais(
        photos,
        320,
        226,
        tema.paleta(),
        IdentityData("Ensaio", "Estúdio", "site.example"),
        seed=17,
    )

    assert cover.used_photo_ids == ("strong-a", "different-b", "similar-a")
    cover.imagem.close()
    for photo in photos:
        photo.image.close()


def test_manual_plan_order_is_authoritative_even_when_a_later_photo_is_safer(
    monkeypatch,
):
    from provas import capas

    first = Image.new("RGB", (180, 100), (190, 40, 40))
    second = Image.new("RGB", (100, 180), (40, 190, 40))
    first.info["manual_order"] = True
    second.info["manual_order"] = True

    def frame(image, target_size, preferred_focus):
        return FrameResult(
            image.resize(target_size),
            CropRect(0.0, 0.0, 1.0, 1.0),
            (),
            0,
            image is second,
        )

    monkeypatch.setattr(capas, "frame_for_mask", frame)
    cover = capas.gerar_curvas_editoriais(
        [capas.CoverPhoto("first", first), capas.CoverPhoto("second", second)],
        320,
        226,
        tema.paleta(),
        IdentityData("Ensaio", "Estúdio", "site.example"),
        seed=19,
    )

    assert cover.used_photo_ids == ("first", "second")
    assert any(warning.code == "rosto_em_area_de_risco" for warning in cover.warnings)
    cover.imagem.close()
    first.close()
    second.close()


def test_automatic_association_and_pixels_are_deterministic_for_same_seed(monkeypatch):
    from provas import capas

    images = [
        Image.new("RGB", (100, 180), color)
        for color in ((190, 30, 30), (30, 190, 30), (30, 30, 190))
    ]
    photos = [capas.CoverPhoto(str(index), image) for index, image in enumerate(images)]
    monkeypatch.setattr(capas, "frame_for_mask", _safe_frame)
    arguments = (
        photos,
        320,
        226,
        tema.paleta(),
        IdentityData("Ensaio", "Estúdio", "site.example"),
    )

    first = capas.gerar_curvas_editoriais(*arguments, seed=23)
    second = capas.gerar_curvas_editoriais(*arguments, seed=23)

    assert first.used_photo_ids == second.used_photo_ids
    assert first.warnings == second.warnings
    assert first.imagem.tobytes() == second.imagem.tobytes()
    first.imagem.close()
    second.imagem.close()
    for image in images:
        image.close()


def test_document_embedded_identity_skips_all_legacy_cover_overlays_but_keeps_metadata(
    tmp_path,
):
    from provas.documento import Documento, Tipografia

    image = Image.new("RGB", (320, 226), (28, 42, 58))
    payload = io.BytesIO()
    image.save(payload, format="JPEG", quality=90)
    output = tmp_path / "embedded-cover.pdf"
    document = Documento(
        "Título incorporado",
        "Subtítulo legado",
        True,
        Tipografia(),
        None,
        nota_capa="NOTA LEGADA",
        estudio="Estúdio incorporado",
        site="site-legado.example",
        modo="fotolivro",
    )

    document.capa(
        payload.getvalue(),
        7,
        "CHAMADA LEGADA",
        identity_embedded=True,
    )
    page = document.pdf[0]
    assert page.rect.width == pytest.approx(tema.A4_PAISAGEM[0], abs=0.01)
    assert page.rect.height == pytest.approx(tema.A4_PAISAGEM[1], abs=0.01)
    assert page.get_text().strip() == ""
    assert page.get_image_rects(page.get_images(full=True)[0]) == [page.rect]
    document.salvar(str(output))

    with pymupdf.open(output) as pdf:
        assert pdf.page_count == 1
        assert pdf.metadata["title"] == "Título incorporado — fotolivro"
        assert pdf.metadata["author"] == "Estúdio incorporado"
    image.close()


def test_motor_render_cover_retains_ids_metadata_identity_seed_and_warnings(
    tmp_path, image_factory, monkeypatch
):
    from provas import capas, motor
    from provas.identidade_capa import CoverWarning
    from provas.modelos import BookPlan, PhotoInfo

    first_path = image_factory("first.jpg", size=(100, 180), color=(180, 30, 30))
    second_path = image_factory("second.jpg", size=(180, 100), color=(30, 30, 180))
    photos = {
        str(first_path): PhotoInfo(
            str(first_path), str(first_path), "first", 100, 180, 0,
            sharpness=0.8, exposure=0.7, density=0.6, quality=0.9,
            similarity_group=4,
        ),
        str(second_path): PhotoInfo(
            str(second_path), str(second_path), "second", 180, 100, 1,
            sharpness=0.4, exposure=0.5, density=0.6, quality=0.7,
            similarity_group=8,
        ),
    }
    plan = BookPlan(73, "fotolivro", tuple(photos), ())
    config = motor.Config(
        str(tmp_path),
        titulo="Ensaio orbital",
        estudio="Estúdio Fanara",
        site="fanara.example",
        estilo_capa="curvas_editoriais",
        cover_ids=tuple(photos),
    ).com_padroes()
    document = motor._new_editorial_document(config, plan.mode)
    warning = CoverWarning("logo_ausente", "Logotipo ausente")
    observed = []

    def fake_generate(style, items, width, height, palette, *, identity, seed):
        observed.append((style, items, width, height, palette, identity, seed))
        return capas.Capa(
            Image.new("RGB", (width, height), (24, 36, 48)),
            0.34,
            identity_embedded=True,
            warnings=(warning,),
            used_photo_ids=tuple(item.id for item in items),
        )

    monkeypatch.setattr(capas, "gerar", fake_generate)
    try:
        rendered = motor._render_cover(document, config, plan, photos)

        assert rendered.warnings == (warning,)
        assert rendered.classic_photo_id == ""
        assert rendered.classic_photo_target is None
        assert len(observed) == 1
        style, items, width, height, palette, identity, seed = observed[0]
        assert style == "curvas_editoriais"
        assert [item.id for item in items] == list(plan.cover_photo_ids)
        assert all(isinstance(item, capas.CoverPhoto) for item in items)
        assert items[0].image.info["quality"] == 0.9
        assert items[0].image.info["similarity_group"] == 4
        assert items[0].image.info["manual_order"] is True
        assert (identity.title, identity.studio, identity.site, identity.logo_path) == (
            config.titulo, config.estudio, config.site, config.logo,
        )
        assert seed == plan.seed
        assert (width, height) == (
            round(document.tamanho[0] / 72 * motor.DPI_MOSAICO),
            round(document.tamanho[1] / 72 * motor.DPI_MOSAICO),
        )
        # The cover keeps its independent identity palette; ``document.p`` is
        # now reserved for the user-selected internal-page appearance.
        assert palette == document.p_capa
        assert document.pdf.page_count == 1
        assert document.pdf[0].get_text().strip() == ""
    finally:
        document.fechar()


def test_curved_preview_and_export_share_pixels_a4_pages_and_warning_boundary(
    tmp_path, image_factory, monkeypatch
):
    from provas import capas, motor
    from provas.modelos import BookPlan, PagePlan

    path = image_factory("orbita.jpg", size=(300, 200), color=(52, 92, 132))
    page = PagePlan(1, "single-landscape", (str(path),), "opening")
    plan = BookPlan(83, "fotolivro", (str(path),), (page,))
    output = tmp_path / "orbita.pdf"
    config = motor.Config(
        str(tmp_path),
        saida=str(output),
        titulo="Ensaio Órbita",
        estudio="Estúdio Fanara",
        site="fanara.example",
        estilo_capa="curvas_editoriais",
        modo="fotolivro",
    )
    monkeypatch.setattr(capas, "frame_for_mask", _unsafe_frame)

    preview = motor.gerar_preview(config, plan, width=420)
    result = motor.exportar(config, plan)

    assert [warning.code for warning in preview.warnings] == [
        "rosto_em_area_de_risco",
        "logo_ausente",
    ]
    assert result.warnings == preview.warnings
    assert len(preview) == 2
    with pymupdf.open(output) as pdf:
        assert pdf.page_count == 2
        assert all(page.rect.width > page.rect.height for page in pdf)
        assert all(page.rect.width == pytest.approx(tema.A4_PAISAGEM[0], abs=0.01) for page in pdf)
        assert all(page.rect.height == pytest.approx(tema.A4_PAISAGEM[1], abs=0.01) for page in pdf)
        scale = 420 / pdf[0].rect.width
        pixmap = pdf[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    assert preview[0].size == (pixmap.width, pixmap.height)
    assert preview[0].tobytes() == pixmap.samples
    for image in preview:
        image.close()


def test_render_fingerprint_includes_cover_style_identity_logo_stat_and_seed(
    tmp_path,
):
    from provas import motor

    logo = tmp_path / "logo.png"
    logo.write_bytes(b"logo-state")
    common = dict(
        pasta=str(tmp_path),
        titulo="Título",
        estudio="Estúdio",
        site="site.example",
        logo=str(logo),
    )
    mosaic = motor.Config(**common, estilo_capa="mosaico")
    curved = motor.Config(**common, estilo_capa="curvas_editoriais")

    baseline = motor.render_style_fingerprint(mosaic, "fotolivro", 101)

    # O estilo da capa ficou de fora: ele não desenha página interna, e incluí-lo
    # fazia a troca de capa descartar a miniatura de todas as páginas.
    assert baseline == motor.render_style_fingerprint(curved, "fotolivro", 101)

    assert baseline != motor.render_style_fingerprint(mosaic, "fotolivro", 102)

    # Título e site também só desenham a capa — provado renderizando, em
    # `test_identidade_da_capa_nao_redesenha_pagina_interna`. Enquanto estavam
    # aqui, cada pausa na digitação recarregava a sessão inteira.
    for campo, valor in (("titulo", "Outro título"), ("site", "outro.example")):
        assert baseline == motor.render_style_fingerprint(
            motor.Config(**{**common, campo: valor}, estilo_capa="mosaico"),
            "fotolivro", 101,
        )

    # O estúdio fica: sem logotipo legível, ele vira a marca d'água das fotos.
    assert baseline != motor.render_style_fingerprint(
        motor.Config(**{**common, "estudio": "Outro"}, estilo_capa="mosaico"),
        "fotolivro", 101,
    )
    logo.write_bytes(b"changed-logo-state")
    assert baseline != motor.render_style_fingerprint(mosaic, "fotolivro", 101)


def test_switching_cover_style_keeps_plan_and_internal_page_pixels(
    tmp_path, image_factory, monkeypatch
):
    from provas import capas, motor
    from provas.modelos import BookPlan, PagePlan

    path = image_factory("internal.jpg", size=(300, 200), color=(84, 104, 124))
    page = PagePlan(1, "single-landscape", (str(path),), "opening")
    plan = BookPlan(109, "fotolivro", (str(path),), (page,))
    original_pages = plan.pages
    common = dict(
        pasta=str(tmp_path),
        titulo="Ensaio",
        estudio="Estúdio",
        site="site.example",
        modo="fotolivro",
    )
    monkeypatch.setattr(capas, "frame_for_mask", _safe_frame)

    mosaic = motor.gerar_preview(motor.Config(**common, estilo_capa="mosaico"), plan, 420)
    curved = motor.gerar_preview(
        motor.Config(**common, estilo_capa="curvas_editoriais"), plan, 420
    )

    assert plan.pages == original_pages
    assert mosaic[0].tobytes() != curved[0].tobytes()
    assert mosaic[1].size == curved[1].size
    assert mosaic[1].tobytes() == curved[1].tobytes()
    for image in (*mosaic, *curved):
        image.close()


def test_cover_text_overflow_blocks_preview_and_export_with_exact_message(
    tmp_path, image_factory, monkeypatch
):
    from provas import capas, motor
    from provas.identidade_capa import CoverTextOverflow
    from provas.modelos import BookPlan, PagePlan

    path = image_factory("overflow.jpg", size=(300, 200), color=(60, 80, 100))
    plan = BookPlan(
        113,
        "fotolivro",
        (str(path),),
        (PagePlan(1, "single-landscape", (str(path),), "opening"),),
    )
    output = tmp_path / "must-not-exist.pdf"
    config = motor.Config(
        str(tmp_path),
        saida=str(output),
        titulo="X" * 500,
        estilo_capa="curvas_editoriais",
        modo="fotolivro",
    )
    monkeypatch.setattr(capas, "frame_for_mask", _safe_frame)
    message = "O texto da capa não cabe. Abrevie o conteúdo antes de exportar."

    with pytest.raises(CoverTextOverflow, match=message.replace(".", r"\.")):
        motor.gerar_preview(config, plan, 420)
    with pytest.raises(CoverTextOverflow, match=message.replace(".", r"\.")):
        motor.exportar(config, plan)

    assert not output.exists()
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("style", ["mosaico", "curvas_editoriais"])
def test_corrupt_logo_warns_without_blocking_preview_or_export(
    tmp_path, image_factory, monkeypatch, style
):
    from provas import capas, motor
    from provas.modelos import BookPlan, PagePlan

    path = image_factory("logo-warning.jpg", size=(300, 200), color=(72, 92, 112))
    corrupt_logo = tmp_path / "corrupt-logo.png"
    corrupt_logo.write_bytes(b"not an image")
    plan = BookPlan(
        127,
        "fotolivro",
        (str(path),),
        (PagePlan(1, "single-landscape", (str(path),), "opening"),),
    )
    output = tmp_path / "corrupt-logo.pdf"
    config = motor.Config(
        str(tmp_path),
        saida=str(output),
        titulo="Ensaio",
        logo=str(corrupt_logo),
        estilo_capa=style,
        modo="fotolivro",
    )
    monkeypatch.setattr(capas, "frame_for_mask", _safe_frame)

    preview = motor.gerar_preview(config, plan, 420)
    result = motor.exportar(config, plan)

    assert [warning.code for warning in preview.warnings] == ["logo_ilegivel"]
    assert result.warnings == preview.warnings
    assert output.exists()
    for image in preview:
        image.close()


def test_legacy_motor_gerar_supports_curved_cover_and_returns_warnings(
    tmp_path, image_factory, monkeypatch
):
    from provas import capas, motor

    image_factory("legacy.jpg", size=(300, 200), color=(64, 84, 104))
    output = tmp_path / "legacy-curved.pdf"
    config = motor.Config(
        str(tmp_path),
        saida=str(output),
        titulo="Ensaio",
        estudio="Estúdio",
        site="site.example",
        estilo_capa="curvas_editoriais",
        marca_dagua=False,
    )
    monkeypatch.setattr(capas, "frame_for_mask", _safe_frame)

    result = motor.gerar(config)

    assert output.exists()
    assert [warning.code for warning in result.warnings] == ["logo_ausente"]
    with pymupdf.open(output) as pdf:
        assert pdf.page_count == 2
        assert pdf[0].rect.width > pdf[0].rect.height
        assert pdf[1].rect.width < pdf[1].rect.height
        assert pdf[0].get_text().strip() == ""
