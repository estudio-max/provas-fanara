"""Local, explainable visual measurements for session photographs."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, Iterable

from PIL import Image, ImageFilter

from . import imagens
from .modelos import PhotoInfo


@dataclass(frozen=True)
class AnalysisResult:
    """Photos successfully measured and recoverable per-file failures."""

    photos: tuple[PhotoInfo, ...]
    failures: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _Measurements:
    foto: imagens.Foto
    index: int
    width: int
    height: int
    sharpness: float
    exposure: float
    density: float
    difference_hash: tuple[int, ...]
    mean_rgb: tuple[float, float, float]


def _cancelled(cancelar: object | None) -> bool:
    if cancelar is None:
        return False
    if callable(cancelar):
        return bool(cancelar())
    is_set = getattr(cancelar, "is_set", None)
    return bool(is_set()) if callable(is_set) else bool(cancelar)


def _notify(progresso: Callable[[tuple[int, str]], None] | None, value: int, message: str) -> None:
    if progresso is not None:
        progresso((max(0, min(100, value)), message))


def _local_variance(gray: Image.Image) -> float:
    """Mean squared difference from a 3px local average, normalized to 0..1."""
    blurred = gray.filter(ImageFilter.BoxBlur(1))
    pixels = _pixels(gray)
    local_mean = _pixels(blurred)
    if not pixels:
        return 0.0
    return sum((pixel - mean) ** 2 for pixel, mean in zip(pixels, local_mean)) / (len(pixels) * 255**2)


def _exposure(gray: Image.Image) -> float:
    histogram = gray.histogram()
    total = max(1, sum(histogram))
    mean = sum(level * count for level, count in enumerate(histogram)) / total / 255
    clipped = sum(histogram[:6]) + sum(histogram[250:])
    balanced = 1.0 - min(1.0, abs(mean - 0.5) * 2)
    return max(0.0, min(1.0, balanced * (1.0 - clipped / total)))


def _edge_density(gray: Image.Image) -> float:
    edges = gray.filter(ImageFilter.FIND_EDGES)
    pixels = _pixels(edges)
    if not pixels:
        return 0.0
    return sum(pixel > 28 for pixel in pixels) / len(pixels)


def _difference_hash(image: Image.Image) -> tuple[tuple[int, ...], tuple[float, float, float]]:
    """A 16x16 RGB directional hash plus its colour centroid for flat scenes."""
    sample = image.resize((17, 16), Image.Resampling.BILINEAR).convert("RGB")
    pixels = _pixels(sample)
    bits: list[int] = []
    for y in range(16):
        row = y * 17
        for x in range(16):
            left, right = pixels[row + x], pixels[row + x + 1]
            bits.extend(int(left[channel] > right[channel]) for channel in range(3))
    source = _pixels(image)
    total = max(1, len(source))
    mean = tuple(sum(pixel[channel] for pixel in source) / total / 255 for channel in range(3))
    return tuple(bits), mean


def _pixels(image: Image.Image) -> list[object]:
    """Use Pillow's non-deprecated accessor while keeping Pillow 10 support."""
    flattened = getattr(image, "get_flattened_data", None)
    return list(flattened() if flattened is not None else image.getdata())


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high <= low:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _similarity_groups(measurements: list[_Measurements]) -> list[int]:
    representatives: list[_Measurements] = []
    groups: list[int] = []
    for measurement in measurements:
        assigned = None
        for group, representative in enumerate(representatives):
            hamming = sum(a != b for a, b in zip(measurement.difference_hash, representative.difference_hash))
            hash_distance = hamming / max(1, len(measurement.difference_hash))
            colour_distance = sum(
                (a - b) ** 2 for a, b in zip(measurement.mean_rgb, representative.mean_rgb)
            ) ** 0.5
            if hash_distance <= 0.10 and colour_distance <= 0.12:
                assigned = group
                break
        if assigned is None:
            assigned = len(representatives)
            representatives.append(measurement)
        groups.append(assigned)
    return groups


def analisar_fotos(
    fotos: Iterable[imagens.Foto],
    cancelar: object | None = None,
    progresso: Callable[[tuple[int, str]], None] | None = None,
) -> AnalysisResult:
    """Measure photos locally, retaining valid inputs when another file is corrupt.

    ``cancelar`` accepts a predicate or a ``threading.Event``-like object.
    ``progresso`` receives ``(percent, filename)`` tuples after each completed read.
    """
    ordered = sorted(fotos, key=lambda foto: imagens._chave_natural(foto.rotulo))
    measurements: list[_Measurements] = []
    failures: list[tuple[str, str]] = []
    total = len(ordered)
    for index, foto in enumerate(ordered):
        if _cancelled(cancelar):
            break
        try:
            image = imagens.redimensionar(imagens.abrir(foto), 512)
            gray = image.convert("L")
            difference_hash, mean_rgb = _difference_hash(image)
            measurements.append(
                _Measurements(
                    foto, index, image.width, image.height, _local_variance(gray), _exposure(gray),
                    _edge_density(gray), difference_hash, mean_rgb,
                )
            )
        except Exception as exc:  # Pillow and RAW preview failures are per-file, not fatal to an album.
            failures.append((os.path.basename(foto.caminho), str(exc)))
        _notify(progresso, round((index + 1) * 100 / max(1, total)), foto.rotulo)

    sharpness = _normalize([measurement.sharpness for measurement in measurements])
    density = _normalize([measurement.density for measurement in measurements])
    similarity = _similarity_groups(measurements)
    photos = []
    for measurement, sharp, dense, group in zip(measurements, sharpness, density, similarity):
        quality = max(0.0, min(1.0, 0.5 * sharp + 0.3 * measurement.exposure + 0.2 * dense))
        photos.append(
            PhotoInfo(
                id=measurement.foto.caminho,
                path=measurement.foto.caminho,
                label=measurement.foto.rotulo,
                width=measurement.width,
                height=measurement.height,
                index=measurement.index,
                sharpness=sharp,
                exposure=measurement.exposure,
                density=dense,
                quality=quality,
                similarity_group=group,
            )
        )
    return AnalysisResult(tuple(photos), tuple(failures))
