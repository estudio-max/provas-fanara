from __future__ import annotations

from dataclasses import FrozenInstanceError
import sys
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw


def _photo(size: tuple[int, int] = (1000, 500)) -> Image.Image:
    image = Image.new("RGB", size, (35, 45, 55))
    draw = ImageDraw.Draw(image)
    draw.rectangle((size[0] // 3, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4), fill=(220, 170, 80))
    return image


def _detector(*boxes):
    return lambda _image: boxes


def test_value_objects_are_normalized_immutable_and_report_geometry():
    from provas.enquadramento import CropRect, FaceBox

    face = FaceBox(0.2, 0.1, 0.4, 0.2, 0.91)
    crop = CropRect(0.1, 0.0, 0.6, 1.0)

    assert face.center == pytest.approx((0.4, 0.2))
    assert crop.contains(face.center)
    assert not crop.contains((0.8, 0.2))
    with pytest.raises(FrozenInstanceError):
        face.x = 0.3  # type: ignore[misc]


def test_frame_keeps_central_confident_face_inside_safe_area():
    from provas.enquadramento import FaceBox, frame_for_mask

    image = _photo()
    face = FaceBox(0.42, 0.30, 0.12, 0.25, 0.95)
    result = frame_for_mask(image, (400, 600), (0.5, 0.5), detector=_detector(face))

    assert result.image.size == (400, 600)
    assert result.face_boxes == (face,)
    assert result.faces_protected == 1
    assert result.safe is True
    assert result.crop.contains(face.center)


def test_frame_moves_only_as_far_as_needed_to_protect_face_near_edge():
    from provas.enquadramento import FaceBox, frame_for_mask

    image = _photo()
    face = FaceBox(0.88, 0.30, 0.04, 0.20, 0.98)
    result = frame_for_mask(image, (400, 600), (0.5, 0.5), detector=_detector(face))

    expected_minimum_x = face.x + face.width - result.crop.width * 0.92
    assert result.crop.x == pytest.approx(expected_minimum_x)
    assert result.faces_protected == 1
    assert result.safe is True


def test_frame_protects_multiple_faces_when_they_fit_together():
    from provas.enquadramento import FaceBox, frame_for_mask

    image = _photo((1200, 600))
    faces = (
        FaceBox(0.29, 0.25, 0.08, 0.22, 0.93),
        FaceBox(0.61, 0.28, 0.07, 0.20, 0.88),
    )
    result = frame_for_mask(image, (600, 600), (0.5, 0.5), detector=_detector(*faces))

    assert result.faces_protected == 2
    assert result.safe is True


def test_frame_returns_deterministic_best_crop_when_faces_cannot_all_fit():
    from provas.enquadramento import FaceBox, frame_for_mask

    image = _photo((1200, 600))
    faces = (
        FaceBox(0.04, 0.25, 0.08, 0.20, 0.94),
        FaceBox(0.88, 0.25, 0.08, 0.20, 0.93),
    )

    first = frame_for_mask(image, (500, 700), (0.5, 0.5), detector=_detector(*faces))
    second = frame_for_mask(image, (500, 700), (0.5, 0.5), detector=_detector(*faces))

    assert first.safe is False
    assert first.faces_protected == 1
    assert first.crop == second.crop
    assert first.image.tobytes() == second.image.tobytes()


def test_low_confidence_faces_are_reported_but_ignored_for_protection():
    from provas.enquadramento import FaceBox, frame_for_mask

    image = _photo()
    ignored = FaceBox(0.9, 0.1, 0.08, 0.2, 0.69)
    result = frame_for_mask(image, (400, 600), (0.1, 0.5), detector=_detector(ignored))

    assert result.face_boxes == (ignored,)
    assert result.faces_protected == 0
    assert result.safe is True


def test_no_faces_uses_deterministic_visual_fallback_and_clamped_focus():
    from provas.enquadramento import frame_for_mask

    image = _photo()
    first = frame_for_mask(image, (400, 600), (-5.0, 8.0), detector=_detector())
    second = frame_for_mask(image, (400, 600), (-5.0, 8.0), detector=_detector())

    assert first.crop == second.crop
    assert first.image.tobytes() == second.image.tobytes()
    assert first.crop.x == 0.0
    assert 0.0 <= first.crop.x <= 1.0 - first.crop.width
    assert 0.0 <= first.crop.y <= 1.0 - first.crop.height
    assert first.faces_protected == 0
    assert first.safe is True


@pytest.mark.parametrize(
    "source,target,expected_crop",
    [
        ((1200, 600), (400, 600), (pytest.approx(1 / 3), pytest.approx(1.0))),
        ((600, 1200), (600, 400), (pytest.approx(1.0), pytest.approx(1 / 3))),
    ],
)
def test_portrait_and_landscape_crops_preserve_target_aspect(source, target, expected_crop):
    from provas.enquadramento import frame_for_mask

    image = _photo(source)
    result = frame_for_mask(image, target, (0.5, 0.5), detector=_detector())

    assert (result.crop.width, result.crop.height) == expected_crop
    assert result.image.size == target


def test_fractional_crop_is_sampled_directly_without_integer_quantization():
    from provas.enquadramento import frame_for_mask

    image = Image.effect_noise((1000, 500), 70).convert("RGB")
    result = frame_for_mask(image, (400, 600), (0.5, 0.5), detector=_detector())
    box = (
        result.crop.x * image.width,
        result.crop.y * image.height,
        (result.crop.x + result.crop.width) * image.width,
        (result.crop.y + result.crop.height) * image.height,
    )
    expected = image.transform(
        (400, 600),
        Image.Transform.EXTENT,
        box,
        Image.Resampling.BICUBIC,
    )

    try:
        assert result.image.tobytes() == expected.tobytes()
    finally:
        result.image.close()
        expected.close()


def test_frame_does_not_mutate_or_take_ownership_of_original_image():
    from provas.enquadramento import frame_for_mask

    image = _photo()
    before = image.tobytes()
    result = frame_for_mask(image, (320, 480), (0.5, 0.5), detector=_detector())

    assert result.image is not image
    assert image.tobytes() == before
    assert image.size == (1000, 500)
    result.image.close()
    assert image.getpixel((0, 0)) == (35, 45, 55)


@pytest.mark.parametrize(
    "image,target,match",
    [
        (object(), (100, 100), "imagem PIL válida"),
        (_photo(), (0, 100), "tamanho alvo"),
        (_photo(), (100, -1), "tamanho alvo"),
        (_photo(), (100.5, 100), "tamanho alvo"),
    ],
)
def test_frame_rejects_invalid_image_and_target_in_portuguese(image, target, match):
    from provas.enquadramento import frame_for_mask

    with pytest.raises(ValueError, match=match):
        frame_for_mask(image, target, (0.5, 0.5), detector=_detector())


def test_frame_rejects_closed_pil_image_in_portuguese():
    from provas.enquadramento import frame_for_mask

    image = _photo()
    image.close()

    with pytest.raises(ValueError, match="imagem PIL válida"):
        frame_for_mask(image, (100, 100), (0.5, 0.5), detector=_detector())


def test_detect_faces_uses_local_haar_parameters_normalizes_and_sorts(monkeypatch):
    from provas import enquadramento

    calls = {}

    class Cascade:
        def __init__(self, path):
            calls["path"] = path

        def empty(self):
            return False

        def detectMultiScale(self, gray, **kwargs):
            calls["gray_shape"] = gray.shape
            calls["kwargs"] = kwargs
            return [(80, 40, 20, 40), (10, 20, 30, 40)]

    fake_cv2 = SimpleNamespace(
        COLOR_RGB2GRAY=7,
        CascadeClassifier=Cascade,
        cvtColor=lambda array, code: calls.update(code=code, rgb_shape=array.shape) or array[:, :, 0],
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    monkeypatch.setattr(enquadramento, "cascade_path", lambda: "cascade-local.xml")

    boxes = enquadramento.detect_faces(Image.new("RGB", (100, 200)))

    assert [(box.x, box.y, box.width, box.height) for box in boxes] == [
        (0.1, 0.1, 0.3, 0.2),
        (0.8, 0.2, 0.2, 0.2),
    ]
    assert calls == {
        "path": "cascade-local.xml",
        "rgb_shape": (200, 100, 3),
        "code": 7,
        "gray_shape": (200, 100),
        "kwargs": {"scaleFactor": 1.1, "minNeighbors": 5, "minSize": (40, 40)},
    }


def test_detect_faces_reports_missing_cascade_in_portuguese(monkeypatch):
    from provas import enquadramento

    fake_cv2 = SimpleNamespace(COLOR_RGB2GRAY=7, cvtColor=lambda array, code: array[:, :, 0])
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    monkeypatch.setattr(enquadramento, "cascade_path", lambda: "Z:/ausente/cascade.xml")

    with pytest.raises(RuntimeError, match="cascade.*não foi encontrado"):
        enquadramento.detect_faces(Image.new("RGB", (100, 100)))


def test_real_detector_smoke_test_does_not_require_a_face():
    pytest.importorskip("cv2", reason="OpenCV não instalado neste ambiente")
    from provas.enquadramento import detect_faces

    assert isinstance(detect_faces(Image.new("RGB", (80, 80), "white")), tuple)


def test_verifier_lists_numpy_opencv_and_diagnoses_cascade(monkeypatch, capsys):
    import verificar

    assert ("numpy", "NumPy", "1.26") in verificar.DEPENDENCIAS
    assert ("cv2", "OpenCV", "4.10") in verificar.DEPENDENCIAS

    class Cascade:
        def __init__(self, path):
            self.path = path

        def empty(self):
            return False

    fake_cv2 = SimpleNamespace(
        data=SimpleNamespace(haarcascades="C:/opencv/data/"),
        CascadeClassifier=Cascade,
    )
    monkeypatch.setattr(verificar.os.path, "isfile", lambda path: path.endswith("haarcascade_frontalface_default.xml"))

    assert verificar.diagnosticar_cascade(fake_cv2) == 0
    assert "cascade Haar local carregado" in capsys.readouterr().out


def test_verifier_reports_missing_cascade_and_continues_other_diagnostics(monkeypatch, capsys):
    import verificar

    calls = []
    fake_cv2 = SimpleNamespace(data=SimpleNamespace(haarcascades="Z:/ausente/"))
    assert verificar.diagnosticar_cascade(fake_cv2) == 1
    assert "cascade Haar" in capsys.readouterr().out

    monkeypatch.setattr(verificar, "diagnosticar_dependencias", lambda: 1)
    monkeypatch.setattr(verificar, "diagnosticar_cascade", lambda: calls.append("cascade") or 1)
    monkeypatch.setattr(verificar, "testar_escrita", lambda: calls.append("escrita") or 0)
    monkeypatch.setattr(verificar, "diagnosticar_fontes", lambda: calls.append("fontes") or 0)
    monkeypatch.setattr(verificar, "testar_pipeline_editorial", lambda: calls.append("pipeline") or 0)

    assert verificar.main([]) == 1
    assert calls == ["cascade", "escrita", "fontes"]
