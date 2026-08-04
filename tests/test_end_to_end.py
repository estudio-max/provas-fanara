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
from provas.compositor import compose, validate_plan
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


@pytest.fixture(scope="session")
def built_package() -> Path:
    from empacotar import commit_atual, fingerprint_fontes

    package = ROOT / "dist" / "Fotolivro-Windows.zip"
    current = {"git_commit": commit_atual(), "source_sha256": fingerprint_fontes()}
    manifest = None
    if package.is_file():
        try:
            with zipfile.ZipFile(package) as archive:
                manifest = json.loads(archive.read("Fotolivro/BUILD-MANIFEST.json"))
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


def test_packaged_executable_generates_both_modes_outside_source_tree(
    tmp_path: Path, built_package: Path,
):
    package = built_package
    extracted = tmp_path / "pacote-extraido"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(extracted)
    executable = extracted / "Fotolivro" / "Fotolivro.exe"
    session = _make_case(tmp_path, "pacote-sintetico", 6, "mixed")

    clean_environment = os.environ.copy()
    clean_environment["PYTHONPATH"] = ""
    clean_environment["PYTHONNOUSERSITE"] = "1"
    outputs = {}
    package_qa = VISUAL_QA / "packaged"
    package_qa.mkdir(parents=True, exist_ok=True)
    for mode in ("prova", "fotolivro"):
        output = package_qa / f"{mode}.pdf"
        completed = subprocess.run(
            [
                str(executable), str(session), "--modo", mode, "--semente", "77",
                "--qualidade", "leve", "--saida", str(output),
            ],
            cwd=tmp_path,
            env=clean_environment,
            capture_output=True,
            timeout=90,
            check=False,
        )
        assert completed.returncode == 0
        assert output.is_file()
        outputs[mode] = output
        with pymupdf.open(output) as pdf:
            assert pdf.page_count >= 2
            assert all(
                (page.rect.width, page.rect.height) == pytest.approx(A4_LANDSCAPE, abs=0.2)
                for page in pdf
            )

    local = motor.analisar_plano(motor.Config(str(session), modo="fotolivro", semente=77))
    by_id = {photo.id: photo for photo in local.photos}
    with pymupdf.open(outputs["prova"]) as proof_pdf, pymupdf.open(outputs["fotolivro"]) as clean_pdf:
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


def test_packaged_zip_contains_verifiable_source_manifest(built_package: Path):
    from empacotar import commit_atual, fingerprint_fontes

    package = built_package

    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read("Fotolivro/BUILD-MANIFEST.json"))
        executable_sha256 = hashlib.sha256(archive.read("Fotolivro/Fotolivro.exe")).hexdigest()

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
