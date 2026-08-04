from __future__ import annotations

import io
import os
from pathlib import Path
import threading

import pymupdf
import pytest
from PIL import Image, ImageChops, ImageDraw

from provas.modelos import BookPlan, PagePlan


def test_config_editorial_defaults_and_tuple_normalization(tmp_path: Path):
    from provas.motor import Config

    config = Config(str(tmp_path), cover_ids=["a", "b"])

    assert config.modo == "prova"
    assert config.semente == 0
    assert config.cover_ids == ("a", "b")


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


def test_proof_and_clean_export_use_the_same_unwatermarked_cover_image(tmp_path: Path, image_factory):
    from provas import motor

    path = image_factory("cover.jpg", size=(300, 200), color=(50, 70, 90))
    logo_path = tmp_path / "logo.png"
    logo = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
    ImageDraw.Draw(logo).rectangle((4, 4, 115, 35), fill=(0, 0, 0, 255))
    logo.save(logo_path)
    page = PagePlan(1, "single-landscape", (str(path),), "opening")
    config = motor.Config(str(tmp_path), logo=str(logo_path), marca_opacidade=0.6)
    cover_images = []

    for mode in ("prova", "fotolivro"):
        output = tmp_path / f"{mode}.pdf"
        plan = BookPlan(8, mode, (str(path),), (page,))
        motor.exportar(motor.Config(**{**config.__dict__, "saida": str(output)}), plan)
        with pymupdf.open(output) as pdf:
            cover_xref = pdf[0].get_images(full=True)[0][0]
            cover_images.append(pdf.extract_image(cover_xref)["image"])

    assert cover_images[0] == cover_images[1]
