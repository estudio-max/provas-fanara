from __future__ import annotations

from collections.abc import Callable
from itertools import count
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def image_factory(tmp_path: Path) -> Callable[..., Path]:
    """Create deterministic JPG fixtures, including EXIF-oriented/corrupt files."""
    sequence = count(1)

    def create(
        name: str | None = None,
        *,
        color: tuple[int, int, int] = (200, 80, 80),
        size: tuple[int, int] = (200, 300),
        orientation: int | None = None,
        corrupt: bool = False,
    ) -> Path:
        path = tmp_path / (name or f"D61_{next(sequence):04d}.jpg")
        if corrupt:
            path.write_bytes(b"not a JPEG")
            return path

        image = Image.new("RGB", size, color)
        if orientation is None:
            image.save(path, format="JPEG")
        else:
            exif = Image.Exif()
            exif[274] = orientation
            image.save(path, format="JPEG", exif=exif)
        return path

    return create


@pytest.fixture
def photo_factory(image_factory: Callable[..., Path]):
    """Create a synthetic JPG and return it as the application's Foto value."""
    from provas.imagens import Foto

    def create(name: str | None = None, **kwargs) -> Foto:
        path = image_factory(name, **kwargs)
        return Foto(str(path), path.stem)

    return create


@pytest.fixture(autouse=True)
def _limpar_caches_do_motor():
    """As fotos preparadas e as miniaturas vivem em cache de módulo.

    Sem limpar entre testes, um teste enxerga a sessão do anterior e passa (ou
    falha) por motivo errado.
    """
    from provas import motor, preview
    from provas.capas import _classic_face_safe_lembrado

    motor.limpar_cache_de_ativos()
    preview.clear_cache()
    _classic_face_safe_lembrado.cache_clear()
    yield
    motor.limpar_cache_de_ativos()
    preview.clear_cache()
    _classic_face_safe_lembrado.cache_clear()
