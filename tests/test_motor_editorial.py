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

    with pytest.raises(
        ValueError,
        match="Estilo de capa inválido. Use classica, mosaico ou curvas_editoriais.",
    ):
        Config(str(tmp_path), estilo_capa="desconhecido").com_padroes()


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


def test_classica_cover_fields_participate_in_the_render_fingerprint(tmp_path: Path):
    from provas import motor

    base = motor.Config(str(tmp_path))
    baseline = motor._render_style_fingerprint(base, "fotolivro", 19)
    changes = {
        "foto_capa_id": "manual.jpg",
        "capa_foco_x": 0.2,
        "capa_foco_y": 0.8,
        "capa_zoom": 1.7,
        "capa_enquadramento": "manual",
    }

    for field, value in changes.items():
        changed = motor.Config(**{**base.__dict__, field: value})
        assert motor._render_style_fingerprint(changed, "fotolivro", 19) != baseline, field


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
