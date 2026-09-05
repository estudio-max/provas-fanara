from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor
import gc
from pathlib import Path
import threading
import time

import pymupdf
import pytest
from PIL import Image, ImageChops, ImageDraw

from provas.modelos import BookPlan, PagePlan, PhotoInfo


def test_config_editorial_defaults_and_tuple_normalization(tmp_path: Path):
    from provas.motor import Config

    config = Config(str(tmp_path), cover_ids=["a", "b"])

    assert config.modo == "prova"
    assert config.semente == 0
    assert config.cover_ids == ("a", "b")


def test_config_defaults_include_classic_cover_settings(tmp_path: Path):
    from provas.motor import Config

    config = Config(str(tmp_path))

    assert config.estilo_capa == "classica"
    assert config.foto_capa_id == ""
    assert (config.capa_foco_x, config.capa_foco_y, config.capa_zoom) == (0.5, 0.5, 1.0)
    assert config.capa_enquadramento == "automatico"


def test_config_defaults_validate_unknown_cover_style_in_portuguese(tmp_path: Path):
    from provas.motor import Config

    from provas.capas import COVER_STYLES

    with pytest.raises(ValueError) as erro:
        Config(str(tmp_path), estilo_capa="desconhecido").com_padroes()

    # A mensagem nomeia as saídas: quem errou o estilo precisa ver as válidas.
    assert "Estilo de capa inválido" in str(erro.value)
    assert all(estilo in str(erro.value) for estilo in COVER_STYLES)


def test_classica_cover_selection_uses_the_approved_deterministic_priority(monkeypatch):
    from provas import capas

    selection = getattr(capas, "selecionar_foto_classica", None)
    assert callable(selection), "classic cover selection API is missing"

    photos = (
        PhotoInfo("vertical", "vertical.jpg", "vertical", 600, 900, 0, quality=1.0),
        PhotoInfo("unsafe", "unsafe.jpg", "unsafe", 900, 600, 1, quality=1.0),
        PhotoInfo("safe-low", "safe-low.jpg", "safe-low", 900, 600, 2, quality=0.2),
        PhotoInfo(
            "safe-best-b",
            "safe-best-b.jpg",
            "safe-best-b",
            900,
            600,
            4,
            sharpness=0.8,
            exposure=0.7,
            density=0.6,
            quality=0.9,
        ),
        PhotoInfo(
            "safe-best-a",
            "safe-best-a.jpg",
            "safe-best-a",
            900,
            600,
            3,
            sharpness=0.8,
            exposure=0.7,
            density=0.6,
            quality=0.9,
        ),
        PhotoInfo(
            "safe-best-0",
            "safe-best-0.jpg",
            "safe-best-0",
            900,
            600,
            3,
            sharpness=0.8,
            exposure=0.7,
            density=0.6,
            quality=0.9,
        ),
        PhotoInfo(
            "weighted",
            "weighted.jpg",
            "weighted",
            900,
            600,
            5,
            sharpness=1.0,
            exposure=1.0,
            density=1.0,
            quality=0.2,
        ),
    )
    monkeypatch.setattr(
        capas,
        "_classic_face_safe",
        lambda photo: photo.id != "unsafe",
    )

    assert selection((photos[0], photos[2]), "") == "safe-low"
    assert selection((photos[1], photos[2]), "") == "safe-low"
    assert selection((photos[2], photos[6]), "") == "weighted"
    assert selection((photos[3], photos[4]), "") == "safe-best-a"
    assert selection((photos[4], photos[5]), "") == "safe-best-0"
    assert selection(photos, "vertical") == "vertical"
    assert selection(photos, "missing") == "safe-best-0"


def test_classica_selection_rejects_faces_cut_by_the_renderer_crop(tmp_path: Path, monkeypatch):
    from provas import capa_classica as classic
    from provas import capas
    from provas.enquadramento import FaceBox, frame_for_mask

    unsafe_path = tmp_path / "unsafe.jpg"
    safe_path = tmp_path / "safe.jpg"
    with Image.new("RGB", (2000, 1000), (190, 30, 30)) as image:
        image.save(unsafe_path, quality=95)
    with Image.new("RGB", (2000, 1000), (30, 180, 30)) as image:
        image.save(safe_path, quality=95)

    unsafe_faces = (
        FaceBox(0.07, 0.20, 0.035, 0.10, 1.0),
        FaceBox(0.55, 0.20, 0.18, 0.35, 1.0),
    )
    safe_faces = (FaceBox(0.40, 0.20, 0.18, 0.35, 1.0),)

    def detected_faces(image):
        red, green, _blue = image.getpixel((0, 0))
        return unsafe_faces if red > green else safe_faces

    real_frame_for_mask = frame_for_mask
    monkeypatch.setattr(classic.enquadramento, "detect_faces", detected_faces)
    monkeypatch.setattr(
        capas,
        "frame_for_mask",
        lambda image, size, focus: real_frame_for_mask(
            image, size, focus, detector=detected_faces
        ),
    )

    with Image.open(unsafe_path) as source:
        legacy_frame = real_frame_for_mask(
            source, (1344, 825), None, detector=detected_faces
        )
        try:
            assert legacy_frame.safe is True
        finally:
            legacy_frame.image.close()
        weights = tuple(face.width * face.height * face.confidence for face in unsafe_faces)
        total = sum(weights)
        focus_x = sum(face.center[0] * weight for face, weight in zip(unsafe_faces, weights)) / total
        focus_y = sum(face.center[1] * weight for face, weight in zip(unsafe_faces, weights)) / total
        renderer_box = classic.crop_box(
            source.size,
            (1344, 825),
            classic.ClassicCrop(focus_x, focus_y, mode="automatico"),
        )
    small_face = unsafe_faces[0]
    assert small_face.x * 2000 < renderer_box.left

    photos = (
        PhotoInfo("unsafe", str(unsafe_path), "unsafe", 2000, 1000, 0, quality=1.0),
        PhotoInfo("safe", str(safe_path), "safe", 2000, 1000, 1, quality=0.1),
    )
    assert capas.selecionar_foto_classica(photos, "") == "safe"

    resolver = getattr(classic, "resolve_classic_crop_box", None)
    assert callable(resolver)
    assert resolver((2000, 1000), (1344, 825), classic.ClassicCrop(), unsafe_faces) == renderer_box


def test_classica_selection_uses_the_exact_integer_renderer_target(monkeypatch):
    from provas import capa_classica as classic
    from provas import capas
    from provas.enquadramento import FaceBox

    source_size = (8000, 12000)
    ranking_target = (1344, 825)
    renderer_target = (1473, 904)
    ranking_height = source_size[0] * ranking_target[1] / ranking_target[0] / source_size[1]
    edge = 0.00001
    face_height = 0.05
    unsafe_faces = (
        FaceBox(0.40, 0.5 - ranking_height / 2 + edge, 0.20, face_height, 1.0),
        FaceBox(
            0.40,
            0.5 + ranking_height / 2 - edge - face_height,
            0.20,
            face_height,
            1.0,
        ),
    )
    safe_faces = (FaceBox(0.40, 0.45, 0.20, 0.10, 1.0),)

    def faces_inside(box, faces):
        return all(
            face.x * source_size[0] >= box.left
            and face.y * source_size[1] >= box.top
            and (face.x + face.width) * source_size[0] <= box.right
            and (face.y + face.height) * source_size[1] <= box.bottom
            for face in faces
        )

    old_box = classic.resolve_classic_crop_box(
        source_size, ranking_target, classic.ClassicCrop(), unsafe_faces
    )
    real_box = classic.resolve_classic_crop_box(
        source_size, renderer_target, classic.ClassicCrop(), unsafe_faces
    )
    assert faces_inside(old_box, unsafe_faces) is True
    assert faces_inside(real_box, unsafe_faces) is False

    def open_source(photo):
        fill = 0 if photo.caminho == "unsafe" else 1
        return Image.new("1", source_size, fill)

    def detected_faces(image):
        return unsafe_faces if image.getpixel((0, 0)) == 0 else safe_faces

    monkeypatch.setattr(capas.imagens, "abrir", open_source)
    monkeypatch.setattr(classic.enquadramento, "detect_faces", detected_faces)
    photos = (
        PhotoInfo("unsafe", "unsafe", "unsafe", *source_size, 0, quality=1.0),
        PhotoInfo("safe", "safe", "safe", *source_size, 1, quality=0.1),
    )

    assert capas.selecionar_foto_classica(photos, "") == "safe"
    target_for = getattr(classic, "classic_photo_target", None)
    assert callable(target_for)
    assert target_for(1754, 1240) == renderer_target
    assert capas.selecionar_foto_classica(
        photos, "", target_size=renderer_target
    ) == "safe"


def test_classic_preview_exposes_effective_photo_and_exact_pdf_target(
    tmp_path: Path, image_factory, monkeypatch
):
    from provas import capa_classica, capas, motor

    first = image_factory("01-primeira-vertical.jpg", size=(600, 900))
    automatic = image_factory("02-automatica-horizontal.jpg", size=(900, 600))
    plan = BookPlan(
        9,
        "fotolivro",
        (str(first),),
        (
            PagePlan(1, "single-portrait", (str(first),), "opening"),
            PagePlan(2, "single-landscape", (str(automatic),), "ending"),
        ),
    )
    monkeypatch.setattr(capas, "_classic_face_safe", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(capa_classica.enquadramento, "detect_faces", lambda _image: ())

    preview = motor.gerar_preview(
        motor.Config(str(tmp_path), modo="fotolivro", titulo="AURORA", estudio="FANARA"),
        plan,
        width=360,
    )
    document = motor._new_editorial_document(motor.Config(str(tmp_path)), "fotolivro")
    try:
        width = round(document.tamanho[0] / 72 * motor.DPI_MOSAICO)
        height = round(document.tamanho[1] / 72 * motor.DPI_MOSAICO)
        expected_target = capa_classica.classic_photo_target(width, height)
    finally:
        document.fechar()

    assert preview.classic_photo_id == str(automatic)
    assert preview.classic_photo_target == expected_target
    assert preview.classic_photo_target == (1473, 904)


def test_classica_cover_fields_stay_out_of_the_render_fingerprint(tmp_path: Path):
    """O enquadramento da capa não altera um pixel de página interna.

    Estes campos estavam na assinatura e, a cada ajuste da capa, o aplicativo
    descartava a miniatura de todas as páginas e redesenhava o livro inteiro
    para atualizar uma imagem só.
    """
    from provas import motor

    base = motor.Config(str(tmp_path))
    baseline = motor.render_style_fingerprint(base, "fotolivro", 19)
    changes = {
        "foto_capa_id": "manual.jpg",
        "capa_foco_x": 0.2,
        "capa_foco_y": 0.8,
        "capa_zoom": 1.7,
        "capa_enquadramento": "manual",
    }

    for field, value in changes.items():
        changed = motor.Config(**{**base.__dict__, field: value})
        assert motor.render_style_fingerprint(changed, "fotolivro", 19) == baseline, field


def test_project_round_trip_preserves_curved_editorial_cover_style(tmp_path: Path):
    from provas.motor import Config
    from provas.projeto import ProjectState, load_project, save_project

    config = Config(str(tmp_path), estilo_capa="curvas_editoriais")
    state = ProjectState(config, BookPlan(1, "prova", (), ()))
    destination = tmp_path / "curvas.json"

    save_project(destination, state)

    assert load_project(destination).config.estilo_capa == "curvas_editoriais"


def test_gerar_plano_analyzes_valid_photos_and_composes_configured_plan(tmp_path: Path, image_factory):
    from provas.motor import Config, gerar_plano

    image_factory("1.jpg", size=(200, 300))
    image_factory("2.jpg", size=(200, 300))
    image_factory("quebrada.jpg", corrupt=True)

    plan = gerar_plano(Config(str(tmp_path), modo="fotolivro", semente=17))

    assert plan.seed == 17
    assert plan.mode == "fotolivro"
    assert sorted(Path(photo_id).name for page in plan.pages for photo_id in page.photo_ids) == ["1.jpg", "2.jpg"]


def test_preview_and_export_consume_exact_supplied_plan_without_recomposition(
    tmp_path: Path, image_factory, monkeypatch
):
    from provas import motor

    path = image_factory("exata.jpg", size=(200, 300))
    plan = BookPlan(440, "prova", (), (PagePlan(1, "single-portrait", (str(path),), "opening"),))
    config = motor.Config(str(tmp_path), saida=str(tmp_path / "book.pdf"), capa_mosaico=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("preview/export must not compose a new plan")

    monkeypatch.setattr(motor, "compose", forbidden)
    thumbnails = motor.gerar_preview(config, plan, width=360)
    result = motor.exportar(config, plan)

    assert len(thumbnails) == 1
    assert result.paginas == 1
    with pymupdf.open(result.saida) as pdf:
        assert pdf.page_count == 1
        assert "exata" in pdf[0].get_text()


@pytest.mark.parametrize("failure_point", ["save", "validation"])
def test_export_is_atomic_and_removes_temp_on_failure(
    tmp_path: Path, image_factory, monkeypatch, failure_point: str
):
    from provas import motor

    path = image_factory("photo.jpg", size=(200, 300))
    destination = tmp_path / "existing.pdf"
    original = b"existing bytes must survive"
    destination.write_bytes(original)
    plan = BookPlan(1, "fotolivro", (), (PagePlan(1, "single-portrait", (str(path),), "opening"),))
    config = motor.Config(str(tmp_path), saida=str(destination), capa_mosaico=False)

    if failure_point == "save":
        def fail_save(self, output):
            Path(output).write_bytes(b"partial")
            raise OSError("disk full")

        monkeypatch.setattr(motor.documento.Documento, "salvar", fail_save)
    else:
        def fail_validation(*args, **kwargs):
            raise ValueError("invalid PDF")

        monkeypatch.setattr(motor, "_validate_export", fail_validation)

    with pytest.raises((OSError, ValueError)):
        motor.exportar(config, plan)

    assert destination.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_export_reports_progress_and_honors_cancellation(tmp_path: Path, image_factory):
    from provas import motor

    path = image_factory("photo.jpg", size=(200, 300))
    plan = BookPlan(1, "prova", (), (PagePlan(1, "single-portrait", (str(path),), "opening"),))
    config = motor.Config(str(tmp_path), saida=str(tmp_path / "cancelled.pdf"), capa_mosaico=False)
    cancelled = threading.Event()
    cancelled.set()
    events: list[tuple[int, int, str]] = []

    with pytest.raises(motor.Cancelado):
        motor.exportar(config, plan, progresso=lambda *args: events.append(args), cancelar=cancelled)

    assert not Path(config.saida).exists()
    assert not list(tmp_path.glob("*.tmp"))
    assert events == []


def test_export_rejects_a_plan_that_references_an_unreadable_photo(tmp_path: Path, image_factory):
    from provas import motor

    path = image_factory("broken.jpg", corrupt=True)
    plan = BookPlan(1, "prova", (), (PagePlan(1, "single-portrait", (str(path),), "opening"),))
    config = motor.Config(str(tmp_path), saida=str(tmp_path / "broken.pdf"), capa_mosaico=False)

    with pytest.raises(ValueError, match="plano.*não puderam ser lidas"):
        motor.exportar(config, plan)

    assert not Path(config.saida).exists()


def test_watermark_is_baked_into_proof_jpeg_only(tmp_path: Path, image_factory):
    from provas import motor

    path = image_factory("plain.jpg", size=(300, 200), color=(60, 60, 60))
    logo_path = tmp_path / "logo.png"
    logo = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
    ImageDraw.Draw(logo).rectangle((4, 4, 115, 35), fill=(0, 0, 0, 255))
    logo.save(logo_path)
    page = PagePlan(1, "single-landscape", (str(path),), "opening")
    proof = BookPlan(4, "prova", (), (page,))
    clean = BookPlan(4, "fotolivro", (), (page,))
    config = motor.Config(str(tmp_path), logo=str(logo_path), marca_opacidade=0.5)

    proof_assets, _ = motor._prepare_render_assets(config.com_padroes(), proof)
    clean_assets, _ = motor._prepare_render_assets(config.com_padroes(), clean)
    proof_jpeg = proof_assets[str(path)].jpeg
    clean_jpeg = clean_assets[str(path)].jpeg

    assert proof_jpeg[:2] == clean_jpeg[:2] == b"\xff\xd8"
    with Image.open(path) as source, Image.open(io.BytesIO(proof_jpeg)) as marked, Image.open(io.BytesIO(clean_jpeg)) as unmarked:
        marked_difference = ImageChops.difference(source.convert("RGB"), marked.convert("RGB")).getbbox()
        clean_difference = ImageChops.difference(source.convert("RGB"), unmarked.convert("RGB")).getbbox()
    assert marked_difference is not None
    assert clean_difference is None


def test_proof_without_external_logo_uses_discreet_text_watermark(tmp_path: Path, image_factory):
    from provas import motor

    path = image_factory("sem-logo.jpg", size=(600, 400), color=(70, 70, 70))
    page = PagePlan(1, "single-landscape", (str(path),), "opening")
    proof = BookPlan(5, "prova", (), (page,))
    clean = BookPlan(5, "fotolivro", (), (page,))
    config = motor.Config(str(tmp_path), logo="", marca_opacidade=0.24)

    proof_assets, _ = motor._prepare_render_assets(config.com_padroes(), proof)
    clean_assets, _ = motor._prepare_render_assets(config.com_padroes(), clean)

    with Image.open(io.BytesIO(proof_assets[str(path)].jpeg)) as marked, Image.open(
        io.BytesIO(clean_assets[str(path)].jpeg)
    ) as unmarked:
        difference = ImageChops.difference(marked.convert("RGB"), unmarked.convert("RGB"))
        assert difference.getbbox() is not None
        changed = sum(pixel != (0, 0, 0) for pixel in difference.get_flattened_data())
        assert changed > marked.width * marked.height * 0.01


@pytest.mark.parametrize("with_cover", [True, False])
def test_corrupt_proof_logo_uses_text_watermark_and_warns_once_in_preview_and_export(
    tmp_path: Path, image_factory, with_cover: bool
):
    from provas import motor

    photo = image_factory("retrato.jpg", size=(300, 450), color=(70, 70, 70))
    corrupt_logo = tmp_path / "logo-corrompido.png"
    corrupt_logo.write_bytes(b"isto nao e uma imagem")
    page = PagePlan(1, "single-portrait", (str(photo),), "opening")
    plan = BookPlan(17, "prova", (str(photo),), (page,))
    output = tmp_path / "prova.pdf"
    config = motor.Config(
        str(tmp_path),
        saida=str(output),
        titulo="Retratos",
        logo=str(corrupt_logo),
        estudio="Estúdio Fanara",
        modo="prova",
        estilo_capa="curvas_editoriais",
        capa_mosaico=with_cover,
    )

    preview = motor.gerar_preview(config, plan, width=320)
    result = motor.exportar(config, plan)

    expected = "O logotipo não pôde ser lido; a capa foi criada sem ele."
    assert [warning.message for warning in preview.warnings] == [expected]
    assert [warning.message for warning in result.warnings] == [expected]
    assert output.exists()
    for image in preview:
        image.close()


def test_textual_watermark_uses_ascii_fallback_when_no_unicode_font_is_available(monkeypatch):
    from provas import imagens

    monkeypatch.setattr(imagens, "_FONT_CANDIDATES", ())

    _, label = imagens._fonte_marca("PROVA PARA SELEÇÃO")

    assert label == "PROVA PARA SELECAO"


def test_analysis_plan_result_keeps_recoverable_failure_details(tmp_path: Path, image_factory):
    from provas import motor

    image_factory("valida.jpg", size=(200, 300))
    image_factory("corrompida.jpg", corrupt=True)

    result = motor.analisar_plano(motor.Config(str(tmp_path), modo="prova", semente=9))

    assert result.plan.seed == 9
    assert len(result.photos) == 1
    assert result.failures[0][0] == "corrompida.jpg"
    assert result.failures[0][1]


def test_preview_includes_exact_export_cover_before_internal_pages(tmp_path: Path, image_factory):
    from provas import motor

    paths = tuple(
        image_factory(f"capa-{index}.jpg", size=(300, 200), color=(60 + index * 20, 80, 100))
        for index in range(1, 5)
    )
    plan = BookPlan(
        6,
        "fotolivro",
        tuple(map(str, paths)),
        (PagePlan(1, "quad-grid", tuple(map(str, paths)), "opening"),),
    )
    output = tmp_path / "com-capa.pdf"
    config = motor.Config(
        str(tmp_path), saida=str(output), titulo="Capa coerente", modo="fotolivro"
    )

    thumbnails = motor.gerar_preview(config, plan, width=420)
    motor.exportar(config, plan)

    assert len(thumbnails) == len(plan.pages) + 1
    with pymupdf.open(output) as pdf:
        assert pdf.page_count == len(thumbnails)
        scale = 420 / pdf[0].rect.width
        rendered = pdf[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    assert thumbnails[0].size == (rendered.width, rendered.height)
    assert thumbnails[0].tobytes() == rendered.samples


def test_proof_and_clean_export_use_the_same_unwatermarked_cover_image(tmp_path: Path, image_factory):
    from provas import motor

    path = image_factory("cover.jpg", size=(300, 200), color=(50, 70, 90))
    logo_path = tmp_path / "logo.png"
    logo = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
    ImageDraw.Draw(logo).rectangle((4, 4, 115, 35), fill=(0, 0, 0, 255))
    logo.save(logo_path)
    page = PagePlan(1, "single-landscape", (str(path),), "opening")
    config = motor.Config(
        str(tmp_path),
        titulo="Capa",
        logo=str(logo_path),
        marca_opacidade=0.6,
        estilo_capa="curvas_editoriais",
    )
    cover_images = []

    for mode in ("prova", "fotolivro"):
        output = tmp_path / f"{mode}.pdf"
        plan = BookPlan(8, mode, (str(path),), (page,))
        motor.exportar(motor.Config(**{**config.__dict__, "saida": str(output)}), plan)
        with pymupdf.open(output) as pdf:
            cover_xref = pdf[0].get_images(full=True)[0][0]
            cover_images.append(pdf.extract_image(cover_xref)["image"])

    assert cover_images[0] == cover_images[1]


def test_preview_pixels_match_export_with_custom_render_style(tmp_path: Path, image_factory):
    from provas import motor, preview

    preview.clear_cache()
    path = image_factory("styled.jpg", size=(200, 300), color=(180, 50, 80))
    plan = BookPlan(21, "fotolivro", (), (PagePlan(1, "single-portrait", (str(path),), "opening"),))
    output = tmp_path / "styled.pdf"
    config = motor.Config(
        str(tmp_path), saida=str(output), capa_mosaico=False, cor_fundo="#1B4265",
        titulo="Estilo", subtitulo="Compartilhado", estudio="Fanara",
    )

    thumbnail = motor.gerar_preview(config, plan, width=420)[0]
    motor.exportar(config, plan)

    with pymupdf.open(output) as pdf:
        scale = 420 / pdf[0].rect.width
        pixmap = pdf[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    assert thumbnail.size == (pixmap.width, pixmap.height)
    assert thumbnail.tobytes() == pixmap.samples


def _wcag_contrast(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    def luminance(color: tuple[float, float, float]) -> float:
        channels = tuple(
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in color
        )
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize(
    ("name", "hex_color"),
    (("branco", "#FFFFFF"), ("cinza", "#D2D2D2"), ("preto", "#111215")),
)
def test_page_background_presets_resolve_wcag_contrast_palettes(name: str, hex_color: str):
    from provas import tema

    assert tema.PAGE_BACKGROUNDS[name] == hex_color
    palette = tema.paleta_paginas(name)

    assert tema.escrever_hex(palette.fundo) == hex_color
    assert _wcag_contrast(palette.texto, palette.fundo) >= 4.5
    assert _wcag_contrast(palette.apagado, palette.fundo) >= 4.5
    assert _wcag_contrast(palette.acento, palette.fundo) >= 4.5
    assert _wcag_contrast(palette.filete, palette.fundo) >= 3.0
    assert _wcag_contrast(palette.moldura, palette.fundo) >= 3.0


def test_page_background_palette_rejects_unknown_value_in_portuguese():
    from provas import tema

    with pytest.raises(ValueError, match="Fundo das páginas inválido"):
        tema.paleta_paginas("azul")


def test_cancellation_after_atomic_replace_returns_success(tmp_path: Path, image_factory, monkeypatch):
    from provas import motor

    path = image_factory("committed.jpg", size=(200, 300))
    output = tmp_path / "committed.pdf"
    plan = BookPlan(31, "prova", (), (PagePlan(1, "single-portrait", (str(path),), "opening"),))
    config = motor.Config(str(tmp_path), saida=str(output), capa_mosaico=False)
    cancelled = threading.Event()
    real_replace = os.replace

    def replace_then_cancel(source, destination):
        real_replace(source, destination)
        cancelled.set()

    monkeypatch.setattr(motor.os, "replace", replace_then_cancel)

    result = motor.exportar(config, plan, cancelar=cancelled)

    assert result.saida == str(output)
    assert output.exists()


def test_non_overwrite_export_preserves_destination_created_during_render(
    tmp_path: Path, image_factory, monkeypatch
):
    from provas import motor

    photo = image_factory("race.jpg", size=(200, 300))
    output = tmp_path / "race.pdf"
    plan = BookPlan(37, "prova", (), (PagePlan(1, "single-portrait", (str(photo),), "opening"),))
    config = motor.Config(str(tmp_path), saida=str(output), capa_mosaico=False)
    real_validate = motor._validate_export
    sentinel = b"CRIADO-DEPOIS-DA-CHECAGEM"

    def create_racing_destination(temporary: str, expected_pages: int) -> None:
        real_validate(temporary, expected_pages)
        output.write_bytes(sentinel)

    monkeypatch.setattr(motor, "_validate_export", create_racing_destination)

    with pytest.raises(FileExistsError, match="já existe.*--sobrescrever"):
        motor.exportar(config, plan, sobrescrever=False)

    assert output.read_bytes() == sentinel
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob("*.tmp"))


def test_repeated_same_destination_exports_serialize_only_publication(
    tmp_path: Path, image_factory, monkeypatch
):
    from provas import motor

    path = image_factory("concurrent.jpg", size=(200, 300))
    output = tmp_path / "shared.pdf"
    plan = BookPlan(41, "fotolivro", (), (PagePlan(1, "single-portrait", (str(path),), "opening"),))
    config = motor.Config(str(tmp_path), saida=str(output), capa_mosaico=False)
    barrier = threading.Barrier(2)
    real_validate = motor._validate_export
    temp_paths: list[str] = []
    lock = threading.Lock()
    active_destinations: set[str] = set()
    real_replace = os.replace

    def synchronized_validation(temp_path, expected_pages):
        real_validate(temp_path, expected_pages)
        with lock:
            temp_paths.append(temp_path)
        barrier.wait(timeout=5)

    monkeypatch.setattr(motor, "_validate_export", synchronized_validation)

    def reject_overlapping_replace(source, destination):
        canonical = os.path.normcase(os.path.realpath(os.path.abspath(destination)))
        with lock:
            if canonical in active_destinations:
                raise PermissionError(5, "overlapping publication", destination)
            active_destinations.add(canonical)
        try:
            time.sleep(0.015)
            real_replace(source, destination)
        finally:
            with lock:
                active_destinations.remove(canonical)

    monkeypatch.setattr(motor.os, "replace", reject_overlapping_replace)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = []
        for _ in range(12):
            futures = [executor.submit(motor.exportar, config, plan) for _ in range(2)]
            results.extend(future.result(timeout=10) for future in futures)

    assert all(result.saida == str(output) for result in results)
    assert len(set(temp_paths)) == 24
    assert all(Path(path).parent == tmp_path and Path(path).suffix == ".tmp" for path in temp_paths)
    assert not list(tmp_path.glob("*.tmp"))
    gc.collect()
    assert not motor._PUBLICATION_LOCKS
    if os.name == "nt":
        assert motor._canonical_destination(str(output).upper()) == motor._canonical_destination(str(output))


def test_distinct_destinations_publish_independently(tmp_path: Path, image_factory, monkeypatch):
    from provas import motor

    path = image_factory("parallel.jpg", size=(200, 300))
    plan = BookPlan(42, "fotolivro", (), (PagePlan(1, "single-portrait", (str(path),), "opening"),))
    configs = [
        motor.Config(str(tmp_path), saida=str(tmp_path / f"distinct-{index}.pdf"), capa_mosaico=False)
        for index in range(2)
    ]
    barrier = threading.Barrier(2)
    real_validate = motor._validate_export
    real_replace = os.replace
    guard = threading.Lock()
    active = 0
    max_active = 0

    def synchronized_validation(temp_path, expected_pages):
        real_validate(temp_path, expected_pages)
        barrier.wait(timeout=5)

    def observe_replace(source, destination):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.04)
            real_replace(source, destination)
        finally:
            with guard:
                active -= 1

    monkeypatch.setattr(motor, "_validate_export", synchronized_validation)
    monkeypatch.setattr(motor.os, "replace", observe_replace)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda config: motor.exportar(config, plan), configs))

    assert len(results) == 2
    assert max_active == 2
    assert all(Path(config.saida).exists() for config in configs)
    assert not list(tmp_path.glob("*.tmp"))


def _page_cycle_plan(paths: tuple[Path, ...], mode: str) -> BookPlan:
    return BookPlan(
        97,
        mode,
        (),
        (
            PagePlan(1, "single-landscape", (str(paths[0]),), "opening"),
            PagePlan(2, "pair-asymmetric-left", (str(paths[1]), str(paths[2])), "sequence"),
            PagePlan(3, "single-landscape", (str(paths[3]),), "ending"),
        ),
    )


def _tracking_page_loader(opened: list[str], closed: list[str]):
    def load(photo_id: str) -> Image.Image:
        opened.append(photo_id)
        image = Image.new("RGB", (360, 240), (90, 120, 150))
        original_close = image.close

        def close() -> None:
            closed.append(photo_id)
            original_close()

        image.close = close  # type: ignore[method-assign]
        return image

    return load


@pytest.mark.parametrize("mode", ("prova", "fotolivro"))
def test_page_cycle_renders_only_selected_page_and_preserves_other_page_plans(
    tmp_path: Path, image_factory, monkeypatch, mode: str,
):
    from provas import motor

    paths = tuple(
        image_factory(f"pagina-{index}.jpg", size=(360, 240), color=(30 * index, 80, 140))
        for index in range(1, 5)
    )
    plan = _page_cycle_plan(paths, mode)
    opened: list[str] = []
    closed: list[str] = []
    monkeypatch.setattr(motor, "_open_photo", _tracking_page_loader(opened, closed))

    result = motor.ciclar_preview_pagina(motor.Config(str(tmp_path), modo=mode), plan, 2, 720)

    assert set(opened) == set(plan.pages[1].photo_ids)
    assert result.plan.pages[:1] == plan.pages[:1]
    assert result.plan.pages[2:] == plan.pages[2:]
    assert result.page_number == 2
    assert result.thumbnail.size[0] == 720
    assert sorted(closed) == sorted(opened)


def test_page_cycle_supports_long_photo_names_and_matches_its_exported_pdf_page(
    tmp_path: Path, image_factory,
):
    from provas import motor

    paths = tuple(
        image_factory(
            f"casamento-na-fazenda-com-familia-e-amigos-registro-{index:02d}.jpg",
            size=(360, 240),
            color=(30 * index, 80, 140),
        )
        for index in range(1, 5)
    )
    plan = _page_cycle_plan(paths, "prova")
    output = tmp_path / "page-cycle.pdf"
    config = motor.Config(str(tmp_path), saida=str(output), modo="prova", capa_mosaico=False)

    result = motor.ciclar_preview_pagina(config, plan, 2, 720)
    motor.exportar(config, result.plan)

    with pymupdf.open(output) as pdf:
        page = pdf[1]
        scale = 720 / page.rect.width
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    assert result.thumbnail.size == (pixmap.width, pixmap.height)
    assert result.thumbnail.tobytes() == pixmap.samples


def test_page_cycle_reports_selected_unreadable_file_without_opening_other_pages(
    tmp_path: Path, image_factory, monkeypatch,
):
    from provas import motor

    paths = tuple(image_factory(f"arquivo-{index}.jpg", size=(360, 240)) for index in range(1, 5))
    plan = _page_cycle_plan(paths, "fotolivro")
    opened: list[str] = []

    def unreadable(photo_id: str) -> Image.Image:
        opened.append(photo_id)
        raise OSError("arquivo de imagem ilegível")

    monkeypatch.setattr(motor, "_open_photo", unreadable)

    with pytest.raises(OSError, match="arquivo de imagem ilegível"):
        motor.ciclar_preview_pagina(motor.Config(str(tmp_path), modo="fotolivro"), plan, 2, 420)
    assert opened == [plan.pages[1].photo_ids[0]]


def test_page_cycle_honors_cancellation_before_opening_any_photo(
    tmp_path: Path, image_factory, monkeypatch,
):
    from provas import motor

    paths = tuple(image_factory(f"cancelar-{index}.jpg", size=(360, 240)) for index in range(1, 5))
    plan = _page_cycle_plan(paths, "prova")
    opened: list[str] = []
    monkeypatch.setattr(motor, "_open_photo", lambda photo_id: opened.append(photo_id))
    cancelled = threading.Event()
    cancelled.set()

    with pytest.raises(motor.Cancelado):
        motor.ciclar_preview_pagina(
            motor.Config(str(tmp_path), modo="prova"), plan, 2, 420, cancelar=cancelled,
        )
    assert opened == []


def test_mudar_so_a_identidade_nao_reprepara_as_fotografias(tmp_path, image_factory, monkeypatch):
    """Preparar as fotos custa segundos; título e site não mudam nenhuma delas.

    Sem isto, cada pausa na digitação relia a pasta, reanalisava nitidez e
    exposição e recodificava todas as imagens — o que tornava os campos de
    identidade praticamente impossíveis de preencher numa sessão grande.
    """
    from dataclasses import replace

    from provas import motor

    for indice in range(4):
        image_factory(f"foto-{indice}.jpg", size=(300, 450))
    motor.limpar_cache_de_ativos()
    config = motor.Config(str(tmp_path), titulo="A", estudio="Estúdio", site="a.com.br",
                          qualidade="leve", semente=3).com_padroes()
    plano = motor.analisar_plano(config).plan

    preparos = []
    original = motor._analisar_config
    monkeypatch.setattr(
        motor, "_analisar_config",
        lambda *args, **kwargs: (preparos.append(1), original(*args, **kwargs))[1],
    )

    motor.gerar_preview(config, plano, width=200)
    assert len(preparos) == 1, "a primeira prévia precisa preparar as fotos"

    for campo, valor in (("titulo", "Outro"), ("site", "outro.com.br"),
                         ("estilo_capa", "jornada"), ("subtitulo", "hoje")):
        motor.gerar_preview(replace(config, **{campo: valor}), plano, width=200)
        assert len(preparos) == 1, f"{campo} não muda foto nenhuma e repreparou tudo"

    # A marca d'água é gravada nos pixels: mudar o estúdio muda cada fotografia.
    motor.gerar_preview(replace(config, estudio="Outro"), plano, width=200)
    assert len(preparos) == 2, "trocar o estúdio muda a marca d'água e exige repreparar"


def test_foto_substituida_na_pasta_invalida_as_fotos_preparadas(tmp_path, image_factory):
    """Cache que não vê o arquivo mudar entrega imagem velha, que é pior que lento."""
    from provas import motor

    caminho = image_factory("foto.jpg", size=(300, 450))
    image_factory("outra.jpg", size=(300, 450))
    motor.limpar_cache_de_ativos()
    config = motor.Config(str(tmp_path), qualidade="leve", semente=3).com_padroes()
    plano = motor.analisar_plano(config).plan
    antes = motor._prepare_render_assets(config, plano)[0]
    chaves_antes = {pid: bytes(ativo.jpeg) for pid, ativo in antes.items()}

    Image.new("RGB", (300, 450), (10, 200, 40)).save(caminho)
    os.utime(caminho, (os.stat(caminho).st_atime, os.stat(caminho).st_mtime + 5))
    depois = motor._prepare_render_assets(config, plano)[0]

    alvo = str(caminho)
    assert alvo in depois
    assert bytes(depois[alvo].jpeg) != chaves_antes[alvo], "entregou a foto antiga"


@pytest.mark.parametrize("estilo", ["fluir", "toscana", "neon", "jornada"])
def test_capa_editorial_recebe_a_resolucao_que_vai_ser_impressa(estilo, tmp_path, image_factory, monkeypatch):
    """A capa saía borrada: a foto vinha reduzida a 320px e era ampliada 5x.

    320px serve ao mosaico, que monta ladrilhos pequenos. Estes estilos usam a
    fotografia grande — em `fluir` ela ocupa a capa inteira.
    """
    from provas import capas, motor

    for indice in range(3):
        image_factory(f"foto-{indice}.jpg", size=(1600, 2400))
    motor.limpar_cache_de_ativos()
    config = motor.Config(str(tmp_path), estilo_capa=estilo, titulo="T", estudio="E",
                          site="e.com.br", modo="fotolivro", marca_dagua=False,
                          mostrar_codigos=False, qualidade="leve", semente=5).com_padroes()
    plano = motor.analisar_plano(config).plan

    recebidas: list[tuple[int, int]] = []
    original = capas.gerar

    def espiar(nome, miniaturas, largura, altura, *args, **kwargs):
        recebidas.extend(
            (item.image if hasattr(item, "image") else item).size for item in miniaturas
        )
        recebidas.append(("alvo", largura, altura))
        return original(nome, miniaturas, largura, altura, *args, **kwargs)

    monkeypatch.setattr(motor.capas, "gerar", espiar)
    motor.gerar_preview(config, plano, width=200)

    alvo = next(item for item in recebidas if item[0] == "alvo")
    tamanhos = [item for item in recebidas if item[0] != "alvo"]
    assert tamanhos, "a capa editorial precisa receber alguma fotografia"
    for largura, altura in tamanhos:
        assert max(largura, altura) >= max(alvo[1], alvo[2]), (
            f"{estilo} recebeu {largura}x{altura} para uma capa {alvo[1]}x{alvo[2]}"
        )
