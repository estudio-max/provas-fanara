"""Caminhos e geração determinística dos recursos oficiais do aplicativo."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys

PRODUCT_NAME = "Fanara - Fotolivro"
_SOURCE_SHA256 = "238ab90b9ad95451b1f888b864e4b6880cddafbfebf6d9ef20f711e3f6fcbe5c"
_BRAND_RGB = (218, 66, 101)
_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
_MASTER_SIZE = 1024
_SUPERSAMPLING = 3
_SAFE_AREA = 0.04


def caminho(nome: str) -> Path:
    """Resolve um ativo em código-fonte ou no diretório temporário do PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "assets" / nome


def _brand_bounds(image: Image.Image) -> tuple[int, int, int, int]:
    from PIL import Image

    rgb = image.convert("RGB")
    xs: list[int] = []
    ys: list[int] = []
    for index, pixel in enumerate(rgb.get_flattened_data()):
        if max(abs(channel - official) for channel, official in zip(pixel, _BRAND_RGB)) <= 8:
            xs.append(index % rgb.width)
            ys.append(index // rgb.width)
    if not xs:
        raise ValueError("A fonte oficial não contém a silhueta rosa esperada.")
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def gerar_identidade_oficial(fonte: Path, simbolo: Path, icone: Path) -> None:
    """Derive PNG/ICO sem alterar o RGB interno da arte oficial.

    O monograma aberto toca as bordas da fonte; por isso o alfa externo usa a
    silhueta convexa do rosa, e não flood-fill branco, que apagaria o ``ef``.
    """
    from PIL import Image, ImageDraw, ImageOps

    if sha256(fonte.read_bytes()).hexdigest() != _SOURCE_SHA256:
        raise ValueError("A fonte do símbolo Fanara não corresponde ao arquivo autorizado.")

    with Image.open(fonte) as opened:
        source = opened.convert("RGBA")
        source.load()
    try:
        left, top, right, bottom = _brand_bounds(source)
        work_size = (source.width * _SUPERSAMPLING, source.height * _SUPERSAMPLING)
        work = source.resize(work_size, Image.Resampling.LANCZOS)
        mask = Image.new("L", work_size, 0)
        silhouette_inset = 2 * _SUPERSAMPLING
        ImageDraw.Draw(mask).ellipse(
            (
                left * _SUPERSAMPLING + silhouette_inset,
                top * _SUPERSAMPLING + silhouette_inset,
                right * _SUPERSAMPLING - silhouette_inset - 1,
                bottom * _SUPERSAMPLING - silhouette_inset - 1,
            ),
            fill=255,
        )
        work.putalpha(mask)

        master_size = _MASTER_SIZE * _SUPERSAMPLING
        inset = round(master_size * _SAFE_AREA)
        available = master_size - 2 * inset
        contained = ImageOps.contain(
            work,
            (available, available),
            Image.Resampling.LANCZOS,
        )
        master = Image.new("RGBA", (master_size, master_size), (0, 0, 0, 0))
        master.alpha_composite(
            contained,
            ((master_size - contained.width) // 2, (master_size - contained.height) // 2),
        )
        derived = master.resize((_MASTER_SIZE, _MASTER_SIZE), Image.Resampling.LANCZOS)
        simbolo.parent.mkdir(parents=True, exist_ok=True)
        icone.parent.mkdir(parents=True, exist_ok=True)
        derived.save(simbolo, "PNG", optimize=False, compress_level=9)
        derived.save(icone, "ICO", sizes=[(size, size) for size in _ICON_SIZES])
    finally:
        source.close()
        for name in ("work", "mask", "contained", "master", "derived"):
            image = locals().get(name)
            if image is not None:
                image.close()
