from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from provas.imagens import listar_fotos


def _save(path: Path, colour: tuple[int, int, int], *, detail: bool = False) -> None:
    image = Image.new("RGB", (120, 180), colour)
    if detail:
        draw = ImageDraw.Draw(image)
        for x in range(0, image.width, 8):
            draw.line((x, 0, image.width - x - 1, image.height - 1), fill=(255, 255, 255), width=2)
    image.save(path)


def test_analisar_fotos_keeps_natural_source_order_and_indices(tmp_path):
    _save(tmp_path / "D61_0010.jpg", (80, 80, 80))
    _save(tmp_path / "D61_0002.jpg", (100, 100, 100))
    _save(tmp_path / "D61_0001.jpg", (120, 120, 120))

    from provas.analise import analisar_fotos

    result = analisar_fotos(listar_fotos(str(tmp_path)))

    assert [photo.label for photo in result.photos] == ["D61_0001", "D61_0002", "D61_0010"]
    assert [photo.index for photo in result.photos] == [0, 1, 2]


def test_analisar_fotos_reports_corrupt_files_without_dropping_valid_photos(tmp_path):
    valid = tmp_path / "D61_0001.jpg"
    broken = tmp_path / "D61_0002.jpg"
    _save(valid, (120, 120, 120))
    broken.write_bytes(b"not an image")

    from provas.analise import analisar_fotos
    from provas.imagens import Foto

    result = analisar_fotos([Foto(str(valid), "D61_0001"), Foto(str(broken), "D61_0002")])

    assert [photo.label for photo in result.photos] == ["D61_0001"]
    assert result.failures and result.failures[0][0] == "D61_0002.jpg"
    assert result.failures[0][1]


def test_analisar_fotos_normalizes_exposure_and_sharpness_signals(tmp_path):
    _save(tmp_path / "dark.jpg", (5, 5, 5))
    _save(tmp_path / "flat.jpg", (130, 130, 130))
    _save(tmp_path / "detail.jpg", (130, 130, 130), detail=True)

    from provas.analise import analisar_fotos

    photos = {photo.label: photo for photo in analisar_fotos(listar_fotos(str(tmp_path))).photos}

    assert all(0.0 <= photo.exposure <= 1.0 for photo in photos.values())
    assert all(0.0 <= photo.sharpness <= 1.0 for photo in photos.values())
    assert photos["detail"].sharpness > photos["flat"].sharpness
    assert photos["dark"].exposure < photos["flat"].exposure


def test_analisar_fotos_assigns_same_similarity_group_to_visual_duplicates(tmp_path):
    _save(tmp_path / "one.jpg", (60, 120, 200), detail=True)
    _save(tmp_path / "two.jpg", (60, 120, 200), detail=True)
    _save(tmp_path / "other.jpg", (200, 80, 40))

    from provas.analise import analisar_fotos

    photos = {photo.label: photo for photo in analisar_fotos(listar_fotos(str(tmp_path))).photos}

    assert photos["one"].similarity_group == photos["two"].similarity_group
    assert photos["one"].similarity_group != photos["other"].similarity_group


def test_analisar_fotos_honours_cancellation_and_reports_progress(tmp_path):
    for index in range(4):
        _save(tmp_path / f"D61_{index:04d}.jpg", (100 + index, 100, 100))
    progress: list[tuple[int, str]] = []
    calls = 0

    def cancelled() -> bool:
        nonlocal calls
        calls += 1
        return calls > 2

    from provas.analise import analisar_fotos

    result = analisar_fotos(listar_fotos(str(tmp_path)), cancelar=cancelled, progresso=progress.append)

    assert 0 < len(result.photos) < 4
    assert progress
    assert all(0 <= value <= 100 and message for value, message in progress)
