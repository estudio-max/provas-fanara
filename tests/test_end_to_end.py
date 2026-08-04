from __future__ import annotations

import io
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


def test_packaged_executable_generates_both_modes_outside_source_tree(tmp_path: Path):
    package = ROOT / "dist" / "Fotolivro-Windows.zip"
    assert package.is_file(), "gere dist/Fotolivro-Windows.zip antes da gate E2E"
    extracted = tmp_path / "pacote-extraido"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(extracted)
    executable = extracted / "Fotolivro" / "Fotolivro.exe"
    session = _make_case(tmp_path, "pacote-sintetico", 6, "mixed")

    clean_environment = os.environ.copy()
    clean_environment["PYTHONPATH"] = ""
    clean_environment["PYTHONNOUSERSITE"] = "1"
    for mode in ("prova", "fotolivro"):
        output = tmp_path / f"pacote-{mode}.pdf"
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
        with pymupdf.open(output) as pdf:
            assert pdf.page_count >= 2
            assert all(page.rect.width > page.rect.height for page in pdf)


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
