from __future__ import annotations

import io
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pymupdf
import pytest
from PIL import Image, ImageDraw

from provas import motor
from provas.ciclo_paginas import alternativas_da_pagina, ciclar_pagina
from provas.compositor import compose, validate_plan
from provas.modelos import BookPlan, PagePlan
from provas.projeto import ProjectState, load_project, save_project
from provas.templates import catalog


ROOT = Path(__file__).parents[1]
VISUAL_QA = ROOT / "tmp" / "visual-qa"
A4_LANDSCAPE = (841.89, 595.28)
CASES = (
    ("24-verticais", 24, "portrait", 1201),
    ("24-horizontais", 24, "landscape", 2402),
    ("32-mistas", 32, "mixed", 3203),
)


def _synthetic_image(path: Path, index: int, orientation: str, *, detail: bool) -> None:
    size = (400, 600) if orientation == "portrait" else (600, 400)
    hue = ((index * 67) % 205 + 25, (index * 101) % 205 + 25, (index * 149) % 205 + 25)
    image = Image.new("RGB", size, hue)
    drawing = ImageDraw.Draw(image)
    if detail:
        step = 16
        for coordinate in range(-size[1], size[0], step):
            drawing.line((coordinate, 0, coordinate + size[1], size[1]), fill=(245, 245, 245), width=4)
    else:
        inset = 36 + index % 5 * 7
        drawing.rectangle((inset, inset, size[0] - inset, size[1] - inset), outline=(20, 20, 24), width=10)
    drawing.rectangle((14, 14, min(size[0] - 14, 250), 54), fill=(250, 250, 250))
    drawing.text((24, 27), path.stem[:34], fill=(10, 10, 12))
    image.save(path, format="JPEG", quality=95, subsampling=0)
    image.close()


def _make_case(root: Path, name: str, total: int, orientation: str) -> Path:
    session = root / name / "fotos"
    session.mkdir(parents=True, exist_ok=True)
    for index in range(total):
        current = (
            "portrait" if orientation == "portrait"
            else "landscape" if orientation == "landscape"
            else "portrait" if index % 2 == 0
            else "landscape"
        )
        label = (
            "FANARA_NOME_EXTREMAMENTE_LONGO_PARA_VALIDAR_LEGENDA_SEM_ESTOURO_0000"
            if index == 0
            else f"FANARA_{index:04d}_{'DETALHE' if index % 3 else 'PLANO_AMPLO'}"
        )
        _synthetic_image(session / f"{label}.jpg", index, current, detail=index % 3 != 0)

    # Two distinct filenames intentionally carry identical pixels. They must be
    # recognized as similar, yet both remain independent editorial photographs.
    shutil.copyfile(session / "FANARA_0004_DETALHE.jpg", session / "FANARA_0005_DETALHE.jpg")
    return session


def _make_curved_case(root: Path, count: int, *, name: str = "curvas") -> Path:
    """Create a small, unique mixed-orientation set for the curved-cover gate."""
    session = root / name / "fotos"
    session.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        orientation = "portrait" if index % 2 == 0 else "landscape"
        _synthetic_image(
            session / f"ORBITA_{index + 1:02d}.jpg",
            index + 40,
            orientation,
            detail=index % 3 != 0,
        )
    return session


def _render_at_width(page: pymupdf.Page, width: int) -> Image.Image:
    scale = width / page.rect.width
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _assert_image_sequence_identity(actual: list[Image.Image], expected: list[Image.Image]) -> None:
    assert len(actual) == len(expected), "identidade: quantidade de streams divergente"
    for index, (actual_image, expected_image) in enumerate(zip(actual, expected)):
        distance = _visual_distance(actual_image, expected_image)
        alternatives = [_visual_distance(actual_image, candidate) for candidate in expected]
        assert distance <= 0.045 and distance <= min(alternatives) + 0.004, (
            f"identidade: stream {index} não corresponde à foto planejada "
            f"(distância perceptual {distance:.4f}, melhor alternativa {min(alternatives):.4f})"
        )


def _assert_mode_rendering(source: Image.Image, proof: Image.Image, clean: Image.Image) -> None:
    clean_distance = _visual_distance(source, clean)
    proof_distance = _visual_distance(source, proof)
    mode_distance = _visual_distance(proof, clean)
    assert clean_distance <= 0.045, (
        f"modo limpo alterou pixels além da recompressão esperada ({clean_distance:.4f})"
    )
    assert mode_distance >= 0.001 and proof_distance >= clean_distance + 0.0005, (
        "marca: prova não difere do limpo pela marca d'água esperada "
        f"(prova/limpo={mode_distance:.4f}, prova/fonte={proof_distance:.4f})"
    )


def _visual_distance(left: Image.Image, right: Image.Image) -> float:
    """RMS perceptual distance, robust to dimensions, JPEG noise and alpha."""
    normalized = []
    for source in (left, right):
        rgba = source.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        rgb = background.convert("RGB").resize((48, 48), Image.Resampling.LANCZOS)
        normalized.append(tuple(rgb.get_flattened_data()))
        rgba.close()
        background.close()
        rgb.close()
    squared = sum(
        (a_channel - b_channel) ** 2
        for a_pixel, b_pixel in zip(*normalized)
        for a_channel, b_channel in zip(a_pixel, b_pixel)
    )
    return math.sqrt(squared / (48 * 48 * 3)) / 255


def _pdf_images(pdf: pymupdf.Document, page_index: int) -> list[Image.Image]:
    images = []
    for entry in pdf[page_index].get_images(full=True):
        stream = pdf.extract_image(entry[0])["image"]
        with Image.open(io.BytesIO(stream)) as decoded:
            images.append(decoded.convert("RGB"))
    return images


@pytest.mark.parametrize("mode", ("prova", "fotolivro"))
@pytest.mark.parametrize("background", ("branco", "cinza", "preto"))
@pytest.mark.parametrize("shadow", (False, True))
def test_page_appearance_keeps_cover_photos_and_preview_pdf_identical(
    tmp_path: Path,
    mode: str,
    background: str,
    shadow: bool,
):
    """Appearance is internal-only: the cover and JPEG streams never change."""
    session = _make_case(tmp_path, "aparencia", 6, "mixed")
    base_output = tmp_path / f"base-{mode}.pdf"
    base = motor.Config(
        str(session), saida=str(base_output), modo=mode, estilo_capa="mosaico",
        qualidade="leve", semente=817,
    )
    analysis = motor.analisar_plano(base)
    base_preview = motor.gerar_preview(base, analysis.plan, width=320)
    motor.exportar(base, analysis.plan)

    output = tmp_path / f"{background}-{shadow}-{mode}.pdf"
    configured = motor.Config(**{
        **base.__dict__, "saida": str(output), "fundo_paginas": background, "sombra_fotos": shadow,
    })
    preview = motor.gerar_preview(configured, analysis.plan, width=320)
    motor.exportar(configured, analysis.plan)

    with pymupdf.open(base_output) as base_pdf, pymupdf.open(output) as pdf:
        assert pdf.page_count == base_pdf.page_count == len(preview)
        base_cover = _render_at_width(base_pdf[0], 320)
        cover = _render_at_width(pdf[0], 320)
        try:
            assert cover.tobytes() == base_cover.tobytes() == preview[0].tobytes() == base_preview[0].tobytes()
        finally:
            cover.close()
            base_cover.close()
        for index, page in enumerate(pdf):
            rendered = _render_at_width(page, 320)
            try:
                assert rendered.tobytes() == preview[index].tobytes()
            finally:
                rendered.close()
        for index in range(1, pdf.page_count):
            actual = [pdf.extract_image(image[0])["image"] for image in pdf[index].get_images(full=True)]
            expected = [
                base_pdf.extract_image(image[0])["image"]
                for image in base_pdf[index].get_images(full=True)
            ]
            assert actual == expected

    for image in (*base_preview, *preview):
        image.close()


def test_page_cycle_uses_the_same_page_appearance_as_export(tmp_path: Path):
    session = _make_case(tmp_path, "aparencia-ciclo", 6, "mixed")
    output = tmp_path / "aparencia-ciclo.pdf"
    config = motor.Config(
        str(session), saida=str(output), modo="fotolivro", capa_mosaico=False,
        fundo_paginas="preto", sombra_fotos=True, qualidade="leve", semente=1201,
    )
    analysis = motor.analisar_plano(config)
    cycled = motor.ciclar_preview_pagina(config, analysis.plan, 1, 320)
    motor.exportar(config, cycled.plan)

    with pymupdf.open(output) as pdf:
        rendered = _render_at_width(pdf[cycled.page_number - 1], 320)
        try:
            assert rendered.tobytes() == cycled.thumbnail.tobytes()
        finally:
            rendered.close()
    cycled.thumbnail.close()


@pytest.fixture(scope="session")
def built_package() -> Path:
    from empacotar import commit_atual, fingerprint_fontes
    from provas.recursos import PRODUCT_NAME

    package = ROOT / "dist" / f"{PRODUCT_NAME}-Windows.zip"
    current = {"git_commit": commit_atual(), "source_sha256": fingerprint_fontes()}
    manifest = None
    if package.is_file():
        try:
            with zipfile.ZipFile(package) as archive:
                manifest = json.loads(archive.read(f"{PRODUCT_NAME}/BUILD-MANIFEST.json"))
        except (KeyError, OSError, ValueError, zipfile.BadZipFile):
            manifest = None
    if not isinstance(manifest, dict) or any(manifest.get(key) != value for key, value in current.items()):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "empacotar.py")],
            cwd=ROOT, capture_output=True, text=True, timeout=240, check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
    assert package.is_file()
    return package


def test_package_name_uses_the_approved_windows_artifact_root():
    from empacotar import NOME
    from provas.recursos import PRODUCT_NAME

    assert NOME == PRODUCT_NAME
    assert ROOT / "dist" / f"{PRODUCT_NAME}-Windows.zip" == ROOT / "dist" / "Fanara - Fotolivro-Windows.zip"


@pytest.mark.parametrize(("case_name", "total", "orientation", "seed"), CASES)
@pytest.mark.parametrize("mode", ("prova", "fotolivro"))
def test_complete_editorial_pipeline_is_deterministic_and_visually_coherent(
    tmp_path: Path,
    case_name: str,
    total: int,
    orientation: str,
    seed: int,
    mode: str,
):
    session = _make_case(tmp_path, case_name, total, orientation)
    output_dir = VISUAL_QA / case_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{mode}.pdf"
    config = motor.Config(
        str(session),
        saida=str(output),
        titulo=f"Ensaio editorial {case_name}",
        subtitulo="04.08.2026",
        estudio="Fanara Fotografia",
        site="fanara.example",
        qualidade="leve",
        modo=mode,
        semente=seed,
        marca_dagua=mode == "prova",
        mostrar_codigos=mode == "prova",
    )

    analysis = motor.analisar_plano(config)
    repeated = compose(analysis.photos, mode, seed)
    preview = motor.gerar_preview(config, analysis.plan, width=320)
    result = motor.exportar(config, analysis.plan)

    assert analysis.failures == ()
    assert analysis.plan == repeated
    assert analysis.plan.seed == seed
    assert validate_plan(analysis.plan, analysis.photos) == ()
    assert result.fotos == total
    assert result.falhas == []
    assert len({photo.id for photo in analysis.photos}) == total
    by_label = {photo.label: photo for photo in analysis.photos}
    assert (
        by_label["FANARA_0004_DETALHE"].similarity_group
        == by_label["FANARA_0005_DETALHE"].similarity_group
    )

    planned_ids = [photo_id for page in analysis.plan.pages for photo_id in page.photo_ids]
    assert len(planned_ids) == len(set(planned_ids)) == total
    templates = {template.id: template for template in catalog()}
    dense_run = longest_dense_run = 0
    for page_plan in analysis.plan.pages:
        dense_run = dense_run + 1 if templates[page_plan.template_id].density_class == "dense" else 0
        longest_dense_run = max(longest_dense_run, dense_run)
    assert longest_dense_run <= 2

    by_id = {photo.id: photo for photo in analysis.photos}
    expected_assets, _ = motor._prepare_render_assets(config.com_padroes(), analysis.plan)
    with pymupdf.open(output) as pdf:
        assert pdf.page_count == len(analysis.plan.pages) + 1 == len(preview)
        assert result.paginas == len(analysis.plan.pages)
        for index, pdf_page in enumerate(pdf):
            assert (pdf_page.rect.width, pdf_page.rect.height) == pytest.approx(A4_LANDSCAPE, abs=0.2)
            rendered = _render_at_width(pdf_page, 320)
            try:
                assert preview[index].size == rendered.size
                assert preview[index].tobytes() == rendered.tobytes()
            finally:
                rendered.close()

        for pdf_page, page_plan in zip(tuple(pdf)[1:], analysis.plan.pages):
            images = pdf_page.get_images(full=True)
            rects = [pdf_page.get_image_rects(image)[0] for image in images]
            assert len(images) == len(page_plan.photo_ids)
            for rect, photo_id in zip(rects, page_plan.photo_ids):
                expected_ratio = by_id[photo_id].width / by_id[photo_id].height
                assert rect.width / rect.height == pytest.approx(expected_ratio, rel=1e-3)
            text = pdf_page.get_text()
            for photo_id in page_plan.photo_ids:
                prefix = Path(photo_id).stem[:18]
                assert (prefix in text) is (mode == "prova")
            actual_images = _pdf_images(pdf, pdf_page.number)
            expected_images = []
            try:
                for photo_id in page_plan.photo_ids:
                    with Image.open(io.BytesIO(expected_assets[photo_id].jpeg)) as expected:
                        expected_images.append(expected.convert("RGB"))
                _assert_image_sequence_identity(actual_images, expected_images)
            finally:
                for image in (*actual_images, *expected_images):
                    image.close()

    assert output.exists() and output.stat().st_size > 0


def test_manual_cover_replacement_survives_preview_and_export(tmp_path: Path):
    session = _make_case(tmp_path, "capa-substituivel", 24, "mixed")
    config = motor.Config(str(session), modo="fotolivro", semente=909)
    original = motor.analisar_plano(config)
    replacement_ids = tuple(photo.id for photo in reversed(original.photos[-3:]))
    replaced = compose(original.photos, "fotolivro", 909, replacement_ids)
    output = VISUAL_QA / "capa-substituivel" / "fotolivro.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    replaced_config = motor.Config(**{**config.__dict__, "saida": str(output), "cover_ids": replacement_ids})

    preview = motor.gerar_preview(replaced_config, replaced, width=320)
    motor.exportar(replaced_config, replaced)

    assert replaced.cover_photo_ids[:3] == replacement_ids
    with pymupdf.open(output) as pdf:
        assert pdf.page_count == len(preview) == len(replaced.pages) + 1
        cover = _render_at_width(pdf[0], 320)
        try:
            assert cover.tobytes() == preview[0].tobytes()
        finally:
            cover.close()


def test_classica_preview_matches_pdf_and_missing_manual_falls_back_without_persisting(
    tmp_path: Path,
):
    session = tmp_path / "classica-fallback"
    session.mkdir()
    portrait = session / "01-retrato.jpg"
    landscape = session / "02-horizontal.jpg"
    with Image.new("RGB", (300, 450), (190, 35, 45)) as image:
        image.save(portrait, quality=95)
    with Image.new("RGB", (600, 400), (35, 175, 65)) as image:
        image.save(landscape, quality=95)
    output = tmp_path / "classica-fallback.pdf"
    config = motor.Config(
        str(session),
        saida=str(output),
        titulo="MEMÓRIAS",
        estudio="FANARA ESTÚDIO",
        estilo_capa="classica",
        foto_capa_id="foto-ausente.jpg",
        modo="fotolivro",
        qualidade="leve",
    )
    analysis = motor.analisar_plano(config)
    original_cover_ids = analysis.plan.cover_photo_ids

    preview = motor.gerar_preview(config, analysis.plan, width=320)
    result = motor.exportar(config, analysis.plan)

    assert config.foto_capa_id == "foto-ausente.jpg"
    assert analysis.plan.cover_photo_ids == original_cover_ids
    assert result.warnings == preview.warnings == ()
    assert preview[0].getpixel((2, preview[0].height // 2)) == (255, 255, 255)
    center = preview[0].getpixel((preview[0].width // 2, preview[0].height // 2))
    assert center[1] > center[0] * 2 and center[1] > center[2] * 2
    with pymupdf.open(output) as pdf:
        assert pdf[0].get_text().strip() == ""
        rendered = _render_at_width(pdf[0], 320)
        try:
            assert rendered.size == preview[0].size
            assert rendered.tobytes() == preview[0].tobytes()
        finally:
            rendered.close()
    for image in preview:
        image.close()


def test_classica_manual_photo_wins_and_cover_is_identical_between_modes(tmp_path: Path):
    session = tmp_path / "classica-manual"
    session.mkdir()
    manual = session / "01-manual-vertical.jpg"
    automatic = session / "02-automatic-horizontal.jpg"
    with Image.new("RGB", (300, 450), (185, 35, 45)) as image:
        image.save(manual, quality=95)
    with Image.new("RGB", (600, 400), (35, 175, 65)) as image:
        image.save(automatic, quality=95)
    base = motor.Config(
        str(session),
        titulo="MEMÓRIAS",
        estudio="FANARA ESTÚDIO",
        estilo_capa="classica",
        foto_capa_id=str(manual),
        qualidade="leve",
    )
    analysis = motor.analisar_plano(base)
    original_cover_ids = analysis.plan.cover_photo_ids
    cover_images = []

    for mode in ("prova", "fotolivro"):
        output = tmp_path / f"classica-{mode}.pdf"
        config = motor.Config(**{**base.__dict__, "saida": str(output), "modo": mode})
        plan = BookPlan(analysis.plan.seed, mode, original_cover_ids, analysis.plan.pages)
        motor.exportar(config, plan)
        assert plan.cover_photo_ids == original_cover_ids
        with pymupdf.open(output) as pdf:
            cover_xref = pdf[0].get_images(full=True)[0][0]
            cover_images.append(pdf.extract_image(cover_xref)["image"])
            rendered = _render_at_width(pdf[0], 320)
            try:
                center = rendered.getpixel((rendered.width // 2, rendered.height // 2))
                assert center[0] > center[1] * 2 and center[0] > center[2] * 2
            finally:
                rendered.close()

    assert cover_images[0] == cover_images[1]


def test_classica_switching_cover_style_keeps_internal_page_pixels(tmp_path: Path):
    session = _make_curved_case(tmp_path, 4, name="classica-estilos")
    base = motor.Config(
        str(session), titulo="MEMÓRIAS", estudio="FANARA ESTÚDIO",
        modo="fotolivro", qualidade="leve", semente=812,
    )
    analysis = motor.analisar_plano(base)
    internal_pages: list[tuple[bytes, ...]] = []

    for style in ("classica", "mosaico", "curvas_editoriais"):
        config = motor.Config(**{**base.__dict__, "estilo_capa": style})
        preview = motor.gerar_preview(config, analysis.plan, width=320)
        try:
            internal_pages.append(tuple(image.tobytes() for image in preview[1:]))
        finally:
            for image in preview:
                image.close()

    assert internal_pages[0] == internal_pages[1] == internal_pages[2]


@pytest.mark.parametrize("mode", ("prova", "fotolivro"))
@pytest.mark.parametrize("orientation", ("portrait", "landscape"))
@pytest.mark.parametrize("framing", ("automatico", "manual"))
@pytest.mark.parametrize("title", ("MEMÓRIAS", "MEMÓRIAS DE UMA TARDE DE INVERNO"))
def test_classic_cover_complete_matrix(
    tmp_path: Path, mode: str, orientation: str, framing: str, title: str,
):
    session = tmp_path / "matriz-classica" / "fotos"
    session.mkdir(parents=True)
    for index in range(2):
        _synthetic_image(
            session / f"CAPA_{index + 1:02d}.jpg", index + 80, orientation,
            detail=index == 0,
        )
    photos = tuple(sorted(session.glob("*.jpg")))
    manual_id = str(photos[-1]) if framing == "manual" else ""
    output = tmp_path / f"classica-{mode}-{orientation}-{framing}.pdf"
    config = motor.Config(
        str(session), saida=str(output), titulo=title, estudio="ESTÚDIO FANARA",
        estilo_capa="classica", foto_capa_id=manual_id,
        capa_foco_x=0.72, capa_foco_y=0.38, capa_zoom=1.5,
        capa_enquadramento=framing, modo=mode, qualidade="leve", semente=9441,
    )
    analysis = motor.analisar_plano(config)
    original_plan = analysis.plan

    preview = motor.gerar_preview(config, original_plan, width=320)
    result = motor.exportar(config, original_plan)
    try:
        assert analysis.plan == original_plan
        assert config.foto_capa_id == manual_id
        assert result.warnings == preview.warnings == ()
        assert preview.classic_photo_id
        if framing == "manual":
            assert preview.classic_photo_id == manual_id
        with pymupdf.open(output) as pdf:
            assert pdf.page_count == len(original_plan.pages) + 1
            assert math.isclose(pdf[0].rect.width, A4_LANDSCAPE[0], abs_tol=0.1)
            assert math.isclose(pdf[0].rect.height, A4_LANDSCAPE[1], abs_tol=0.1)
            assert len(pdf[0].get_images(full=True)) == 1
            rendered = _render_at_width(pdf[0], 320)
            try:
                assert rendered.size == preview[0].size
                assert rendered.tobytes() == preview[0].tobytes()
            finally:
                rendered.close()
    finally:
        for image in preview:
            image.close()


@pytest.mark.parametrize("count", range(1, 10))
@pytest.mark.parametrize("mode", ("prova", "fotolivro"))
def test_curved_cover_end_to_end(tmp_path: Path, count: int, mode: str):
    session = _make_curved_case(tmp_path, count, name=f"matriz-{mode}-{count}")
    output = tmp_path / f"curvas-{mode}-{count}.pdf"
    config = motor.Config(
        str(session),
        saida=str(output),
        titulo=f"Órbita {count}",
        estudio="Estúdio Fanara",
        site="fanara.com.br",
        estilo_capa="curvas_editoriais",
        modo=mode,
        marca_dagua=mode == "prova",
        mostrar_codigos=mode == "prova",
        qualidade="leve",
        semente=8100 + count,
    )
    analysis = motor.analisar_plano(config)
    original_pages = analysis.plan.pages
    preview = motor.gerar_preview(config, analysis.plan, width=320)
    result = motor.exportar(config, analysis.plan)

    assert analysis.failures == ()
    assert analysis.plan.pages == original_pages
    assert len(analysis.plan.cover_photo_ids) == count
    assert len(set(analysis.plan.cover_photo_ids)) == count
    assert result.fotos == count
    with pymupdf.open(output) as pdf:
        assert pdf.page_count == len(original_pages) + 1 == len(preview)
        assert all(
            (page.rect.width, page.rect.height) == pytest.approx(A4_LANDSCAPE, abs=0.2)
            for page in pdf
        )
        rendered = _render_at_width(pdf[0], 320)
        try:
            assert rendered.tobytes() == preview[0].tobytes()
        finally:
            rendered.close()
    for image in preview:
        image.close()


def test_invalid_logo_warns_and_exports(tmp_path: Path):
    session = _make_curved_case(tmp_path, 3, name="logo-invalido")
    logo = tmp_path / "logo-invalido.png"
    logo.write_bytes(b"isto nao e uma imagem")
    output = tmp_path / "logo-invalido.pdf"
    config = motor.Config(
        str(session), saida=str(output), titulo="Retratos", logo=str(logo),
        estilo_capa="curvas_editoriais", modo="fotolivro", qualidade="leve",
    )
    analysis = motor.analisar_plano(config)
    original_cover_ids = analysis.plan.cover_photo_ids
    preview = motor.gerar_preview(config, analysis.plan, width=320)
    result = motor.exportar(config, analysis.plan)

    assert result.warnings == preview.warnings
    assert analysis.plan.cover_photo_ids == original_cover_ids
    assert [warning.message for warning in result.warnings] == [
        "O logotipo não pôde ser lido; a capa foi criada sem ele."
    ]
    with pymupdf.open(output) as pdf:
        rendered = _render_at_width(pdf[0], 320)
        try:
            assert rendered.tobytes() == preview[0].tobytes()
        finally:
            rendered.close()
    for image in preview:
        image.close()


def test_overlong_identity_blocks_export(tmp_path: Path):
    from provas.identidade_capa import CoverTextOverflow

    session = _make_curved_case(tmp_path, 1, name="identidade-longa")
    output = tmp_path / "nao-publicar.pdf"
    output.write_bytes(b"PDF anterior preservado")
    previous = output.read_bytes()
    config = motor.Config(
        str(session), saida=str(output), titulo="X" * 500,
        estilo_capa="curvas_editoriais", modo="fotolivro", qualidade="leve",
    )
    analysis = motor.analisar_plano(config)
    original_cover_ids = analysis.plan.cover_photo_ids
    message = "O texto da capa não cabe. Abrevie o conteúdo antes de exportar."

    with pytest.raises(CoverTextOverflow, match="Abrevie") as error:
        motor.exportar(config, analysis.plan)
    assert str(error.value) == message
    assert analysis.plan.cover_photo_ids == original_cover_ids
    assert output.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_missing_logo_keeps_balanced_cover(tmp_path: Path):
    session = _make_curved_case(tmp_path, 6, name="sem-logo")
    output = tmp_path / "sem-logo.pdf"
    config = motor.Config(
        str(session), saida=str(output), titulo="Retratos", estudio="Fanara",
        site="fanara.com.br", logo=str(tmp_path / "nao-existe.png"),
        estilo_capa="curvas_editoriais", modo="fotolivro", qualidade="leve",
    )
    analysis = motor.analisar_plano(config)
    original_cover_ids = analysis.plan.cover_photo_ids
    preview = motor.gerar_preview(config, analysis.plan, width=320)
    result = motor.exportar(config, analysis.plan)

    assert analysis.plan.cover_photo_ids == tuple(dict.fromkeys(analysis.plan.cover_photo_ids))
    assert [warning.message for warning in result.warnings] == [
        "O logotipo não foi encontrado; a capa foi criada sem ele."
    ]
    assert result.warnings == preview.warnings
    assert analysis.plan.cover_photo_ids == original_cover_ids
    with pymupdf.open(output) as pdf:
        rendered = _render_at_width(pdf[0], 320)
        try:
            assert rendered.tobytes() == preview[0].tobytes()
        finally:
            rendered.close()
    for image in preview:
        image.close()


def test_edge_face_is_kept_inside_mask(tmp_path: Path, monkeypatch):
    from provas import capas
    from provas.capa_curvas import layout_orbita, render_mask
    from provas.enquadramento import FaceBox, frame_for_mask

    session = _make_curved_case(tmp_path, 1, name="rosto-na-borda")
    photo_path = next(session.glob("*.jpg"))
    # Near the source edge, but still geometrically protectable by this mask.
    face = FaceBox(0.25, 0.08, 0.22, 0.24, confidence=0.96)
    layout = layout_orbita(1600, 1131, 1)
    slot = layout.slots[0]
    with Image.open(photo_path) as source:
        framed = frame_for_mask(
            source,
            (slot.bounds.width, slot.bounds.height),
            slot.preferred_focus,
            detector=lambda _image: (face,),
        )
    assert framed.safe is True
    assert framed.crop.contains(face.center)
    crop = framed.crop
    face_box = (
        math.floor(slot.bounds.x + (face.x - crop.x) / crop.width * slot.bounds.width),
        math.floor(slot.bounds.y + (face.y - crop.y) / crop.height * slot.bounds.height),
        math.ceil(slot.bounds.x + (face.x + face.width - crop.x) / crop.width * slot.bounds.width),
        math.ceil(slot.bounds.y + (face.y + face.height - crop.y) / crop.height * slot.bounds.height),
    )
    mask = render_mask(slot, (1600, 1131))
    try:
        with mask.crop(face_box) as face_region:
            assert face_region.getextrema()[0] >= 128
    finally:
        mask.close()
        framed.image.close()

    original = capas.frame_for_mask
    monkeypatch.setattr(
        capas,
        "frame_for_mask",
        lambda image, size, focus: original(
            image, size, focus, detector=lambda _image: (face,)
        ),
    )
    config = motor.Config(
        str(session), saida=str(tmp_path / "rosto-na-borda.pdf"), titulo="Retrato",
        estilo_capa="curvas_editoriais", modo="fotolivro", qualidade="leve",
    )
    analysis = motor.analisar_plano(config)
    original_cover_ids = analysis.plan.cover_photo_ids
    preview = motor.gerar_preview(config, analysis.plan, width=320)
    result = motor.exportar(config, analysis.plan)
    assert all(warning.code != "rosto_em_area_de_risco" for warning in result.warnings)
    assert result.warnings == preview.warnings
    assert analysis.plan.cover_photo_ids == original_cover_ids
    with pymupdf.open(config.saida) as pdf:
        rendered = _render_at_width(pdf[0], 320)
        try:
            assert rendered.tobytes() == preview[0].tobytes()
        finally:
            rendered.close()
    for image in preview:
        image.close()


def test_automatic_cover_avoids_face_cut_by_curve_mask(monkeypatch):
    from provas import capas, tema
    from provas.enquadramento import CropRect, FaceBox, FrameResult
    from provas.identidade_capa import IdentityData

    edge = Image.new("RGB", (200, 300), (210, 170, 140))
    centered = Image.new("RGB", (200, 300), (80, 110, 140))

    def framed(image, target_size, _focus):
        face = (
            FaceBox(0.01, 0.01, 0.28, 0.25, 1.0)
            if image is edge
            else FaceBox(0.40, 0.28, 0.22, 0.22, 1.0)
        )
        return FrameResult(
            image.resize(target_size), CropRect(0.0, 0.0, 1.0, 1.0), (face,), 1, True
        )

    monkeypatch.setattr(capas, "frame_for_mask", framed)
    monkeypatch.setattr(capas, "_candidate_score", lambda *_args: (0,))
    cover = capas.gerar_curvas_editoriais(
        [capas.CoverPhoto("borda", edge), capas.CoverPhoto("centro", centered)],
        1600, 1131, tema.paleta(), IdentityData("Retratos", "", ""), seed=24,
    )
    try:
        assert cover.used_photo_ids[0] == "centro"
        assert [warning.code for warning in cover.warnings].count("rosto_em_area_de_risco") == 1
    finally:
        cover.imagem.close()
        edge.close()
        centered.close()


def test_automatic_cover_avoids_logo_over_detected_face(tmp_path: Path, monkeypatch):
    from provas import capas, tema
    from provas.enquadramento import CropRect, FaceBox, FrameResult
    from provas.identidade_capa import IdentityData
    from tests.visual_qa import _qa_logo

    logo = tmp_path / "logo.png"
    _qa_logo(logo, "horizontal")
    covered = Image.new("RGB", (200, 300), (210, 170, 140))
    clear = Image.new("RGB", (200, 300), (80, 110, 140))

    def framed(image, target_size, _focus):
        face = (
            FaceBox(0.25, 0.08, 0.20, 0.15, 1.0)
            if image is covered
            else FaceBox(0.64, 0.30, 0.20, 0.20, 1.0)
        )
        return FrameResult(
            image.resize(target_size), CropRect(0.0, 0.0, 1.0, 1.0), (face,), 1, True
        )

    monkeypatch.setattr(capas, "frame_for_mask", framed)
    monkeypatch.setattr(capas, "_candidate_score", lambda *_args: (0,))
    cover = capas.gerar_curvas_editoriais(
        [capas.CoverPhoto("coberto", covered), capas.CoverPhoto("livre", clear)],
        1600, 1131, tema.paleta(),
        IdentityData("Retratos", "Fanara", "fanara.com.br", str(logo)),
        seed=22,
    )
    try:
        assert cover.used_photo_ids[0] == "livre"
    finally:
        cover.imagem.close()
        covered.close()
        clear.close()


@pytest.mark.parametrize("logo_kind", ("ausente", "corrompido"))
def test_unrenderable_logo_does_not_reorder_automatic_cover(
    tmp_path: Path, monkeypatch, logo_kind: str
):
    from provas import capas, tema
    from provas.enquadramento import CropRect, FaceBox, FrameResult
    from provas.identidade_capa import IdentityData

    logo = tmp_path / "logo.png"
    if logo_kind == "corrompido":
        logo.write_bytes(b"nao e uma imagem")
    covered = Image.new("RGB", (200, 300), (210, 170, 140))
    clear = Image.new("RGB", (200, 300), (80, 110, 140))

    def framed(image, target_size, _focus):
        face = (
            FaceBox(0.25, 0.08, 0.20, 0.15, 1.0)
            if image is covered
            else FaceBox(0.64, 0.30, 0.20, 0.20, 1.0)
        )
        return FrameResult(
            image.resize(target_size), CropRect(0.0, 0.0, 1.0, 1.0), (face,), 1, True
        )

    monkeypatch.setattr(capas, "frame_for_mask", framed)
    monkeypatch.setattr(capas, "_candidate_score", lambda *_args: (0,))
    cover = capas.gerar_curvas_editoriais(
        [capas.CoverPhoto("primeira", covered), capas.CoverPhoto("segunda", clear)],
        1600, 1131, tema.paleta(),
        IdentityData("Retratos", "Fanara", "fanara.com.br", str(logo)),
        seed=23,
    )
    try:
        assert cover.used_photo_ids[0] == "primeira"
        expected = "logo_ausente" if logo_kind == "ausente" else "logo_ilegivel"
        assert [warning.code for warning in cover.warnings] == [expected]
    finally:
        cover.imagem.close()
        covered.close()
        clear.close()


def test_opaque_white_logo_is_renderable_and_protects_its_cover_area(
    tmp_path: Path, monkeypatch,
):
    from provas import capas, tema
    from provas.enquadramento import CropRect, FaceBox, FrameResult
    from provas.identidade_capa import IdentityData

    logo = tmp_path / "logo-branco.png"
    with Image.new("RGB", (120, 40), "white") as white_logo:
        white_logo.save(logo)
    covered = Image.new("RGB", (200, 300), (210, 170, 140))
    clear = Image.new("RGB", (200, 300), (80, 110, 140))

    def framed(image, target_size, _focus):
        face = (
            FaceBox(0.25, 0.08, 0.20, 0.15, 1.0)
            if image is covered
            else FaceBox(0.64, 0.30, 0.20, 0.20, 1.0)
        )
        return FrameResult(
            image.resize(target_size), CropRect(0.0, 0.0, 1.0, 1.0), (face,), 1, True
        )

    monkeypatch.setattr(capas, "frame_for_mask", framed)
    monkeypatch.setattr(capas, "_candidate_score", lambda *_args: (0,))
    cover = capas.gerar_curvas_editoriais(
        [capas.CoverPhoto("primeira", covered), capas.CoverPhoto("segunda", clear)],
        1600, 1131, tema.paleta(),
        IdentityData("Retratos", "Fanara", "fanara.com.br", str(logo)), seed=23,
    )
    try:
        assert cover.used_photo_ids[0] == "segunda"
        assert cover.warnings == ()
    finally:
        cover.imagem.close()
        covered.close()
        clear.close()


def test_manual_cover_choice_survives_regeneration(tmp_path: Path):
    session = _make_curved_case(tmp_path, 9, name="capa-manual-regenerada")
    initial_config = motor.Config(
        str(session), estilo_capa="curvas_editoriais", modo="fotolivro", semente=501,
    )
    initial = motor.analisar_plano(initial_config)
    manual_ids = tuple(reversed(initial.plan.cover_photo_ids))
    regenerated_config = motor.Config(
        str(session), saida=str(tmp_path / "capa-manual.pdf"),
        estilo_capa="curvas_editoriais", modo="fotolivro", semente=777,
        cover_ids=manual_ids, qualidade="leve",
    )
    regenerated = motor.analisar_plano(regenerated_config)
    preview = motor.gerar_preview(regenerated_config, regenerated.plan, width=320)
    motor.exportar(regenerated_config, regenerated.plan)

    assert regenerated.plan.cover_photo_ids == manual_ids
    assert regenerated_config.cover_ids == manual_ids
    with pymupdf.open(regenerated_config.saida) as pdf:
        rendered = _render_at_width(pdf[0], 320)
        try:
            assert rendered.tobytes() == preview[0].tobytes()
        finally:
            rendered.close()
    for image in preview:
        image.close()


def test_packaged_executable_generates_both_modes_outside_source_tree(
    tmp_path: Path, built_package: Path,
):
    from provas.recursos import PRODUCT_NAME

    package = built_package
    extracted = tmp_path / "pacote-extraido"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(extracted)
    executable = extracted / PRODUCT_NAME / f"{PRODUCT_NAME}.exe"
    session = _make_case(tmp_path, "pacote-sintetico", 6, "mixed")

    clean_environment = os.environ.copy()
    clean_environment["PYTHONPATH"] = ""
    clean_environment["PYTHONNOUSERSITE"] = "1"
    outputs = {}
    package_qa = VISUAL_QA / "packaged"
    package_qa.mkdir(parents=True, exist_ok=True)
    for style in ("mosaico", "curvas_editoriais"):
        for mode in ("prova", "fotolivro"):
            output = package_qa / f"{style}-{mode}.pdf"
            completed = subprocess.run(
                [
                    str(executable), str(session), "--modo", mode, "--capa", style,
                    "--titulo", "Sessão local", "--estudio", "Estúdio Fanara",
                        "--site", "fanara.com.br", "--semente", "77",
                        "--qualidade", "leve", "--saida", str(output), "--sobrescrever",
                ],
                cwd=tmp_path,
                env=clean_environment,
                capture_output=True,
                timeout=90,
                check=False,
            )
            assert completed.returncode == 0
            assert output.is_file()
            outputs[(style, mode)] = output
            with pymupdf.open(output) as pdf:
                assert pdf.page_count >= 2
                assert all(
                    (page.rect.width, page.rect.height) == pytest.approx(A4_LANDSCAPE, abs=0.2)
                    for page in pdf
                )

    local = motor.analisar_plano(motor.Config(str(session), modo="fotolivro", semente=77))
    by_id = {photo.id: photo for photo in local.photos}
    for style in ("mosaico", "curvas_editoriais"):
        with pymupdf.open(outputs[(style, "prova")]) as proof_pdf, \
                pymupdf.open(outputs[(style, "fotolivro")]) as clean_pdf:
            assert proof_pdf.page_count == clean_pdf.page_count == len(local.plan.pages) + 1
            for page_index, page_plan in enumerate(local.plan.pages, start=1):
                proof_images = _pdf_images(proof_pdf, page_index)
                clean_images = _pdf_images(clean_pdf, page_index)
                try:
                    assert len(proof_images) == len(clean_images) == len(page_plan.photo_ids)
                    for proof, clean, photo_id in zip(proof_images, clean_images, page_plan.photo_ids):
                        with Image.open(by_id[photo_id].path) as source:
                            _assert_mode_rendering(source, proof, clean)
                    proof_text = proof_pdf[page_index].get_text()
                    clean_text = clean_pdf[page_index].get_text()
                    for photo_id in page_plan.photo_ids:
                        prefix = Path(photo_id).stem[:10]
                        assert prefix in proof_text
                        assert prefix not in clean_text
                finally:
                    for image in (*proof_images, *clean_images):
                        image.close()


def test_visual_baselines_document_the_approved_cases_and_seeds():
    baseline = ROOT / "tests" / "baselines" / "README.md"

    assert baseline.is_file()
    text = baseline.read_text(encoding="utf-8")
    for case_name, total, _orientation, seed in CASES:
        assert case_name in text
        assert str(total) in text
        assert str(seed) in text
    assert "prova" in text.lower()
    assert "fotolivro" in text.lower()


def test_visual_identity_guard_rejects_repeated_same_orientation_image():
    expected = [Image.new("RGB", (400, 600), color) for color in ((220, 40, 40), (40, 80, 220))]
    actual = [expected[0].copy(), expected[0].copy()]
    try:
        with pytest.raises(AssertionError, match="identidade"):
            _assert_image_sequence_identity(actual, expected)
    finally:
        for image in (*expected, *actual):
            image.close()


def test_mode_guard_rejects_proof_without_watermark():
    source = Image.new("RGB", (600, 400), (70, 90, 120))
    clean = source.copy()
    proof_without_watermark = source.copy()
    try:
        with pytest.raises(AssertionError, match="marca"):
            _assert_mode_rendering(source, proof_without_watermark, clean)
    finally:
        source.close()
        clean.close()
        proof_without_watermark.close()


def _make_page_cycle_album(root: Path, orientation: str) -> tuple[BookPlan, tuple[str, ...]]:
    """Build a ten-page album with one, two and four-photo pages to cycle."""
    session = root / f"ciclo-{orientation}"
    session.mkdir()
    paths: list[str] = []
    for index in range(22):
        if orientation == "portrait":
            current = "portrait"
        elif orientation == "landscape":
            current = "landscape"
        else:
            current = "portrait" if index % 2 == 0 else "landscape"
        path = session / f"CICLO_{orientation}_{index:02d}.jpg"
        _synthetic_image(path, index + 60, current, detail=index % 2 == 0)
        paths.append(str(path))

    def page(number: int, template_id: str, count: int, role: str) -> PagePlan:
        start = sum((1, 2, 4, 1, 2, 4, 1, 2, 4)[: number - 1])
        photo_ids = tuple(paths[start : start + count])
        # Deliberately begin multi-photo pages in a non-optimal order so the
        # E2E contract proves that positions, not only templates, can change.
        if count in (2, 4):
            photo_ids = tuple(reversed(photo_ids))
        return PagePlan(number, template_id, photo_ids, role)

    if orientation == "portrait":
        templates = (
            ("single-portrait", 1), ("pair-asymmetric-left", 2), ("quad-left-feature", 4),
            ("single-full", 1), ("pair-portraits", 2), ("quad-grid", 4),
            ("single-portrait", 1), ("pair-breathing", 2), ("quad-columns", 4), ("single-full", 1),
        )
    elif orientation == "landscape":
        templates = (
            ("single-landscape", 1), ("pair-asymmetric-left", 2), ("quad-top-feature", 4),
            ("single-full", 1), ("pair-landscapes", 2), ("quad-grid", 4),
            ("single-landscape", 1), ("pair-breathing", 2), ("quad-top-feature", 4), ("single-full", 1),
        )
    else:
        templates = (
            ("single-full", 1), ("pair-asymmetric-left", 2), ("quad-left-feature", 4),
            ("single-full", 1), ("pair-breathing", 2), ("quad-grid", 4),
            ("single-full", 1), ("pair-asymmetric-right", 2), ("quad-columns", 4), ("single-full", 1),
        )
    roles = ("opening", "sequence", "narrative", "sequence", "narrative", "sequence", "narrative", "sequence", "ending", "ending")
    pages = tuple(page(number, template_id, count, roles[number - 1]) for number, (template_id, count) in enumerate(templates, start=1))
    return BookPlan(661, "fotolivro", (paths[0],), pages), tuple(paths)


@pytest.mark.parametrize("orientation", ("portrait", "landscape", "mixed"))
@pytest.mark.parametrize("mode", ("prova", "fotolivro"))
def test_page_cycle_e2e_keeps_cover_persists_three_of_ten_and_matches_pdf(
    tmp_path: Path, monkeypatch, orientation: str, mode: str,
):
    """The complete per-page flow only reads each selected internal page."""
    plan, photo_paths = _make_page_cycle_album(tmp_path, orientation)
    plan = BookPlan(plan.seed, mode, plan.cover_photo_ids, plan.pages)
    config = motor.Config(
        str(Path(photo_paths[0]).parent), saida=str(tmp_path / f"ciclo-{orientation}-{mode}.pdf"),
        modo=mode, estilo_capa="classica", foto_capa_id=plan.cover_photo_ids[0],
        qualidade="leve", marca_dagua=mode == "prova", mostrar_codigos=mode == "prova",
    )
    original_cover = plan.cover_photo_ids
    original_pages = plan.pages
    selected = (1, 2, 3)
    ratios = {}
    for photo_id in photo_paths:
        with Image.open(photo_id) as image:
            ratios[photo_id] = 2 / 3 if image.height > image.width else 3 / 2
    try:
        for number in selected:
            alternatives = alternativas_da_pagina(plan, number, ratios)
            assert len(alternatives) >= 2
            assert all(set(candidate.photo_ids) == set(plan.pages[number - 1].photo_ids) for candidate in alternatives)
            assert any(candidate != plan.pages[number - 1] for candidate in alternatives)
            current = ciclar_pagina(plan, number, ratios)
            seen = [current.pages[number - 1]]
            for _ in range(len(alternatives) - 1):
                current = ciclar_pagina(current, number, ratios)
                seen.append(current.pages[number - 1])
            assert len(seen) == len(set(seen))
            assert set(seen) == set(alternatives)
            current = ciclar_pagina(current, number, ratios)
            assert current.pages[number - 1] == seen[0]

        opened: list[str] = []
        original_open = motor._open_photo

        def tracked_open(photo_id: str):
            opened.append(photo_id)
            return original_open(photo_id)

        monkeypatch.setattr(motor, "_open_photo", tracked_open)
        results = {}
        for number in selected:
            result = motor.ciclar_preview_pagina(config, plan, number, 420)
            results[number] = result
            plan = result.plan
        assert set(opened) == set().union(*(set(original_pages[number - 1].photo_ids) for number in selected))
        assert all(path not in opened for page in original_pages[3:] for path in page.photo_ids)
        assert plan.cover_photo_ids == original_cover
        assert all(plan.pages[number - 1] != original_pages[number - 1] for number in selected)
        assert plan.pages[3:] == original_pages[3:]

        project = tmp_path / "ciclo.provas.json"
        save_project(project, ProjectState(config, plan, photo_paths))
        assert load_project(project).plan == plan

        monkeypatch.setattr(motor, "_open_photo", original_open)
        motor.exportar(config, plan)
        with pymupdf.open(config.saida) as pdf:
            assert pdf.page_count == 11
            for number, result in results.items():
                rendered = _render_at_width(pdf[number], 420)
                try:
                    assert rendered.tobytes() == result.thumbnail.tobytes()
                finally:
                    rendered.close()
            assert pdf[0].get_images(full=True), "a capa deve continuar renderizada"
            for page in pdf[1:]:
                text = page.get_text()
                assert bool(text.strip()) is (mode == "prova")
    finally:
        for result in locals().get("results", {}).values():
            result.thumbnail.close()


def test_page_cycle_e2e_is_stable_across_python_hash_seeds():
    """The cycle order is reproducible even when interpreter hash randomization changes."""
    script = """
import json
from provas.ciclo_paginas import alternativas_da_pagina
from provas.modelos import BookPlan, PagePlan
plan = BookPlan(661, 'fotolivro', (), (PagePlan(1, 'pair-asymmetric-left', ('v1', 'v2'), 'opening'),))
print(json.dumps([(page.template_id, page.photo_ids) for page in alternativas_da_pagina(plan, 1, {'v1': 2/3, 'v2': 3/4})]))
"""
    outputs = []
    for seed in ("1", "2"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        completed = subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, env=environment,
            capture_output=True, text=True, check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        outputs.append(completed.stdout)
    assert outputs[0] == outputs[1]


def test_page_cycle_e2e_reassigns_photos_to_the_best_compatible_positions():
    """An asymmetric spread changes photo positions without changing its photo set."""
    plan = BookPlan(
        661, "fotolivro", (),
        (PagePlan(1, "pair-asymmetric-left", ("narrow", "wide"), "opening"),),
    )

    alternatives = alternativas_da_pagina(plan, 1, {"narrow": 0.25, "wide": 0.80})

    assert alternatives
    assert all(set(candidate.photo_ids) == {"narrow", "wide"} for candidate in alternatives)
    assert any(candidate.photo_ids == ("wide", "narrow") for candidate in alternatives)


def test_packaged_zip_contains_verifiable_source_manifest(built_package: Path):
    from empacotar import commit_atual, fingerprint_fontes
    from provas.recursos import PRODUCT_NAME

    package = built_package

    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read(f"{PRODUCT_NAME}/BUILD-MANIFEST.json"))
        executable_sha256 = hashlib.sha256(archive.read(f"{PRODUCT_NAME}/{PRODUCT_NAME}.exe")).hexdigest()

    assert manifest["source_sha256"] == fingerprint_fontes()
    assert manifest["git_commit"] == commit_atual()
    assert manifest["executable_sha256"] == executable_sha256


def test_visual_qa_helper_renders_pages_at_120_dpi_and_contact_sheet(tmp_path: Path):
    case = tmp_path / "caso"
    case.mkdir()
    pdf_path = case / "prova.pdf"
    document = pymupdf.open()
    document.new_page(width=A4_LANDSCAPE[0], height=A4_LANDSCAPE[1])
    document.save(pdf_path)
    document.close()

    completed = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "visual_qa.py"), str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    page = case / "prova" / "page-001.png"
    contact_sheet = case / "prova-contact-sheet.png"
    assert page.is_file()
    assert contact_sheet.is_file()
    with Image.open(page) as rendered:
        assert rendered.size == pytest.approx((1403, 992), abs=1)
    assert " / página " not in (ROOT / "tests" / "visual_qa.py").read_text(encoding="utf-8")


def test_visual_qa_curved_case_builds_required_matrix(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable, str(ROOT / "tests" / "visual_qa.py"),
            "--case", "curvas-editoriais", "--dpi", "120", "--output", str(tmp_path),
        ],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    expected = {
        f"count-{count:02d}-{tone}-{logo}-contact-sheet.png"
        for count in (1, 3, 5, 6, 9)
        for tone in ("claros", "escuros", "mistos")
        for logo in ("horizontal", "vertical", "ausente")
    }
    assert expected <= {path.name for path in tmp_path.glob("*-contact-sheet.png")}
    assert (tmp_path / "curvas-editoriais-overview.png").is_file()
    assert all(path.stat().st_size > 0 for path in tmp_path.glob("*.png"))


def test_visual_qa_classic_case_builds_required_matrix(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable, str(ROOT / "tests" / "visual_qa.py"),
            "--case", "capa-classica", "--dpi", "120", "--output", str(tmp_path),
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert len(tuple(tmp_path.glob("*-contact-sheet.png"))) == 6
    assert (tmp_path / "capa-classica-overview.png").is_file()
    assert all(path.stat().st_size > 0 for path in tmp_path.glob("*.png"))


def test_visual_qa_page_cycle_captures_normal_busy_and_unavailable_controls(tmp_path: Path):
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["QT_SCALE_FACTOR"] = "1.25"
    completed = subprocess.run(
        [
            sys.executable, str(ROOT / "tests" / "visual_qa.py"),
            "--case", "ciclo-paginas", "--dpi", "120", "--output", str(tmp_path),
        ],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=120, check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    screenshot = tmp_path / "ui-1093x614-125.png"
    assert screenshot.is_file()
    with Image.open(screenshot) as captured:
        assert captured.size == (1093, 614)
        screenshot_pixels = captured.tobytes()
    contact_sheet = tmp_path / "ciclo-paginas-contact-sheet.png"
    assert contact_sheet.is_file()
    with Image.open(contact_sheet) as captured:
        assert captured.size == (1093, 614)
        assert captured.tobytes() == screenshot_pixels
    qa_state = json.loads((tmp_path / "ciclo-paginas-qa.json").read_text(encoding="utf-8"))
    assert qa_state["scale_factor"] == 1.25
    assert qa_state["scroll_maximum"] > 0
    assert qa_state["scroll_before"] > 0
    assert qa_state["scroll_after"] == qa_state["scroll_before"]


def test_readme_explains_that_pages_without_alternatives_keep_a_disabled_control():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "visível, porém desabilitado" in readme


def test_visual_qa_synthetic_portrait_has_injectable_face_box(tmp_path: Path):
    from tests import visual_qa

    photo = tmp_path / "retrato.jpg"
    visual_qa._qa_photo(photo, 0, "claros")
    with Image.open(photo) as image:
        faces = visual_qa._synthetic_face_detector(image)

    assert len(faces) == 1
    assert faces[0].confidence == 1.0
    assert 0.10 < faces[0].width < 0.30
    assert 0.10 < faces[0].height < 0.30
