from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import provas.capa_classica as classic
from provas.capa_classica import (
    BODONI_PATH,
    CoverTextOverflow,
    ClassicCrop,
    ClassicLayout,
    crop_box,
    layout_classico,
    render_classic_cover,
)
from provas.capas import CoverPhoto
from provas.enquadramento import FaceBox


@pytest.fixture
def photo() -> CoverPhoto:
    image = Image.new("RGB", (6016, 4016), (40, 90, 140))
    return CoverPhoto("D61_0001", image)


def test_official_bodoni_resource_and_license_are_present():
    font = Path(BODONI_PATH)
    license_path = font.with_name("OFL-BodoniModa.txt")

    assert font.name == "BodoniModa[opsz,wght].ttf"
    assert font.read_bytes()[:4] == b"\x00\x01\x00\x00"
    assert "SIL OPEN FONT LICENSE Version 1.1" in license_path.read_text(encoding="utf-8")


def test_layout_matches_approved_a4_proportions_snapshot():
    layout = layout_classico(1600, 1131)

    assert (
        (layout.title.left, layout.title.top, layout.title.width, layout.title.height),
        (layout.studio.left, layout.studio.top, layout.studio.width, layout.studio.height),
        (layout.photo.left, layout.photo.top, layout.photo.width, layout.photo.height),
    ) == (
        (128, 69, 1344, 69),
        (128, 159, 1344, 34),
        (128, 211, 1344, 824),
    )
    assert layout.photo.left == pytest.approx(128, abs=1)
    assert layout.photo.right == pytest.approx(1472, abs=1)
    assert layout.photo.top == pytest.approx(211, abs=1)
    assert layout.photo.bottom == pytest.approx(1036, abs=1)


def test_classic_records_are_immutable():
    with pytest.raises(FrozenInstanceError):
        ClassicCrop().zoom = 2.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        layout_classico(1600, 1131).photo = None  # type: ignore[misc]


@pytest.mark.parametrize("source_size", [(6016, 4016), (4016, 6016)])
def test_manual_crop_covers_frame_and_keeps_focus(source_size):
    box = crop_box(source_size, (1344, 825), ClassicCrop(0.8, 0.3, 1.4, "manual"))

    assert box.width / box.height == pytest.approx(1344 / 825)
    assert 0 <= box.left < box.right <= source_size[0]
    assert 0 <= box.top < box.bottom <= source_size[1]
    assert box.left <= source_size[0] * 0.8 <= box.right
    assert box.top <= source_size[1] * 0.3 <= box.bottom


def test_crop_clamps_edge_focus_without_revealing_empty_pixels():
    left = crop_box((6016, 4016), (1344, 825), ClassicCrop(0.0, 0.0, 2.5, "manual"))
    right = crop_box((6016, 4016), (1344, 825), ClassicCrop(1.0, 1.0, 2.5, "manual"))

    assert (left.left, left.top) == pytest.approx((0.0, 0.0))
    assert (right.right, right.bottom) == pytest.approx((6016.0, 4016.0))
    assert left.width == pytest.approx(right.width)
    assert left.height == pytest.approx(right.height)


def test_zoom_multiplies_fill_scale_from_one_through_two_and_a_half():
    normal = crop_box((6016, 4016), (1344, 825), ClassicCrop(zoom=1.0, mode="manual"))
    zoomed = crop_box((6016, 4016), (1344, 825), ClassicCrop(zoom=2.5, mode="manual"))

    assert zoomed.width == pytest.approx(normal.width / 2.5)
    assert zoomed.height == pytest.approx(normal.height / 2.5)


def test_renderer_uses_detected_face_for_automatic_focus(monkeypatch):
    source = Image.new("RGB", (1000, 500), (30, 60, 90))
    item = CoverPhoto("face-edge", source)
    calls = []

    def detector(image):
        calls.append(image)
        return (FaceBox(0.88, 0.25, 0.10, 0.20, 1.0),)

    monkeypatch.setattr("provas.capa_classica.enquadramento.detect_faces", detector)
    result = render_classic_cover(
        item,
        1600,
        1131,
        "AVENTURAS",
        "ESTÚDIO FANARA",
        ClassicCrop(mode="automatico"),
    )
    try:
        assert calls == [source]
        assert result.identity_embedded is True
        assert result.used_photo_ids == ("face-edge",)
    finally:
        result.imagem.close()
        source.close()


@pytest.mark.parametrize("source_size", [(900, 1400), (1400, 900)])
def test_renderer_handles_accents_both_orientations_and_keeps_caller_image_open(
    source_size, monkeypatch
):
    source = Image.new("RGB", source_size, (23, 87, 149))
    item = CoverPhoto("sessão-á", source)
    monkeypatch.setattr("provas.capa_classica.enquadramento.detect_faces", lambda image: ())

    result = render_classic_cover(
        item,
        1600,
        1131,
        "ÁLBUM DE FÉRIAS",
        "ESTÚDIO SÃO PAULO",
        ClassicCrop(),
    )
    try:
        assert result.imagem.mode == "RGB"
        assert result.imagem.size == (1600, 1131)
        assert result.used_photo_ids == ("sessão-á",)
        assert source.getpixel((0, 0)) == (23, 87, 149)
        layout = layout_classico(1600, 1131)
        assert result.imagem.getpixel((layout.photo.x, layout.photo.y)) == (23, 87, 149)
        assert result.imagem.getpixel((0, 0)) == (255, 255, 255)
    finally:
        result.imagem.close()
        source.close()


def test_manual_renderer_does_not_run_automatic_face_detection(photo, monkeypatch):
    def unexpected(_image):
        raise AssertionError("manual crop must not detect faces")

    monkeypatch.setattr("provas.capa_classica.enquadramento.detect_faces", unexpected)
    result = render_classic_cover(
        photo, 1600, 1131, "AVENTURAS", "ESTÚDIO", ClassicCrop(mode="manual")
    )
    result.imagem.close()
    photo.image.close()


def test_overlong_title_fails_atomically_before_detection(photo, monkeypatch):
    detection_called = False

    def detector(_image):
        nonlocal detection_called
        detection_called = True
        return ()

    monkeypatch.setattr("provas.capa_classica.enquadramento.detect_faces", detector)

    with pytest.raises(CoverTextOverflow, match="Abrevie o título"):
        render_classic_cover(photo, 1600, 1131, "W" * 180, "ESTÚDIO", ClassicCrop())

    assert detection_called is False
    assert photo.image.getpixel((0, 0)) == (40, 90, 140)
    photo.image.close()


def test_overlong_studio_fails_atomically_before_detection_or_rgb_canvas(photo, monkeypatch):
    detection_called = False
    rgb_canvas_created = False
    original_new = Image.new

    def detector(_image):
        nonlocal detection_called
        detection_called = True
        return ()

    def observed_new(mode, size, *args, **kwargs):
        nonlocal rgb_canvas_created
        if mode == "RGB" and size == (1600, 1131):
            rgb_canvas_created = True
        return original_new(mode, size, *args, **kwargs)

    monkeypatch.setattr("provas.capa_classica.enquadramento.detect_faces", detector)
    monkeypatch.setattr("provas.capa_classica.Image.new", observed_new)

    with pytest.raises(CoverTextOverflow, match="Abrevie o estúdio"):
        render_classic_cover(photo, 1600, 1131, "AVENTURAS", "W" * 300, ClassicCrop())

    assert detection_called is False
    assert rgb_canvas_created is False
    assert photo.image.getpixel((0, 0)) == (40, 90, 140)
    photo.image.close()


def test_missing_segoe_ui_light_fails_in_portuguese_before_detection(photo, monkeypatch):
    def unexpected(_image):
        raise AssertionError("missing font must fail before face detection")

    monkeypatch.setattr("provas.capa_classica._SEGOE_UI_LIGHT_PATH", "fonte-ausente.ttf")
    monkeypatch.setattr("provas.capa_classica.enquadramento.detect_faces", unexpected)

    try:
        with pytest.raises(RuntimeError, match="Segoe UI Light não está disponível"):
            render_classic_cover(
                photo,
                1600,
                1131,
                "AVENTURAS",
                "ESTÚDIO",
                ClassicCrop(),
            )
    finally:
        photo.image.close()


def test_studio_tracking_is_exactly_point_two_six_em_with_subpixel_width():
    text = "ESTÚDIO"
    font = classic._studio_font(10)
    tracking = classic._studio_tracking(font)

    with Image.new("L", (1, 1), 0) as measure:
        draw = ImageDraw.Draw(measure)
        glyph_width = sum(draw.textlength(character, font=font) for character in text)
        expected = glyph_width + (len(text) - 1) * 2.6
        actual = classic._tracking_width(draw, text, font, tracking)

    assert tracking == pytest.approx(2.6, abs=1e-12)
    assert actual == pytest.approx(expected, abs=1e-6)
