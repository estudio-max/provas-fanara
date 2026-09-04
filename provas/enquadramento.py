"""Enquadramento local de fotografias com proteção determinística de rostos."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from typing import Callable, Iterable

from PIL import Image


SAFE_INSET = 0.08
MIN_FACE_CONFIDENCE = 0.70
_CASCADE_NAME = "haarcascade_frontalface_default.xml"
_EPSILON = 1e-9


@dataclass(frozen=True)
class FaceBox:
    """Caixa de rosto em coordenadas normalizadas da imagem."""

    x: float
    y: float
    width: float
    height: float
    confidence: float

    def __post_init__(self) -> None:
        _validate_rect(self.x, self.y, self.width, self.height, "rosto")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("A confiança do rosto deve estar normalizada entre 0 e 1.")

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    @classmethod
    def from_pixels(
        cls,
        box: Iterable[int | float],
        image_size: tuple[int, int],
        confidence: float,
    ) -> "FaceBox":
        x, y, width, height = box
        image_width, image_height = image_size
        return cls(
            float(x) / image_width,
            float(y) / image_height,
            float(width) / image_width,
            float(height) / image_height,
            confidence,
        )


@dataclass(frozen=True)
class CropRect:
    """Retângulo de recorte em coordenadas normalizadas da imagem."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        _validate_rect(self.x, self.y, self.width, self.height, "recorte")

    def contains(self, point: tuple[float, float]) -> bool:
        px, py = point
        return (
            self.x - _EPSILON <= px <= self.x + self.width + _EPSILON
            and self.y - _EPSILON <= py <= self.y + self.height + _EPSILON
        )


@dataclass(frozen=True)
class FrameResult:
    """Imagem enquadrada e metadados; o chamador deve fechar ``image``."""

    image: Image.Image
    crop: CropRect
    face_boxes: tuple[FaceBox, ...]
    faces_protected: int
    safe: bool


FaceDetector = Callable[[Image.Image], tuple[FaceBox, ...]]


def _validate_rect(x: float, y: float, width: float, height: float, label: str) -> None:
    values = (x, y, width, height)
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"O {label} deve usar coordenadas normalizadas finitas.")
    if x < 0.0 or y < 0.0 or width < 0.0 or height < 0.0:
        raise ValueError(f"O {label} deve usar coordenadas normalizadas entre 0 e 1.")
    if x + width > 1.0 + _EPSILON or y + height > 1.0 + _EPSILON:
        raise ValueError(f"O {label} deve permanecer dentro da imagem normalizada.")


def _validate_image(image: object) -> Image.Image:
    if not isinstance(image, Image.Image) or image.width <= 0 or image.height <= 0:
        raise ValueError("Forneça uma imagem PIL válida e não vazia.")
    try:
        image.load()
    except Exception as error:
        raise ValueError("Forneça uma imagem PIL válida, aberta e legível.") from error
    return image


def cascade_path() -> str:
    """Retorne o cascade frontal distribuído localmente com o OpenCV."""
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError(
            "OpenCV não está instalado; não foi possível localizar o cascade Haar local."
        ) from error
    base = getattr(getattr(cv2, "data", None), "haarcascades", "")
    return os.path.join(base, _CASCADE_NAME)


def detect_faces(image: Image.Image) -> tuple[FaceBox, ...]:
    """Detecte rostos com o cascade Haar local, sem rede nem modelos externos."""
    image = _validate_image(image)
    try:
        import cv2
        import numpy
    except ImportError as error:
        raise RuntimeError(
            "OpenCV e NumPy são necessários para a detecção local de rostos."
        ) from error

    path = cascade_path()
    try:
        cascade = cv2.CascadeClassifier(path)
    except Exception as error:
        raise RuntimeError(f"O cascade Haar local não foi encontrado em: {path}") from error
    if cascade.empty():
        raise RuntimeError(f"O cascade Haar local não foi encontrado ou não pôde ser carregado: {path}")

    with image.convert("RGB") as rgb:
        array = numpy.asarray(rgb)
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    boxes = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(40, 40),
    )
    ordered = sorted((tuple(map(int, box)) for box in boxes), key=lambda box: box)
    return tuple(FaceBox.from_pixels(box, image.size, 1.0) for box in ordered)


def _crop_dimensions(image_size: tuple[int, int], target_size: tuple[int, int]) -> tuple[float, float]:
    image_width, image_height = image_size
    target_width, target_height = target_size
    image_ratio = image_width / image_height
    target_ratio = target_width / target_height
    if image_ratio >= target_ratio:
        return (target_ratio / image_ratio, 1.0)
    return (1.0, image_ratio / target_ratio)


def _visual_center(image: Image.Image) -> tuple[float, float]:
    """Escolha um centro saliente por contraste local em uma grade pequena."""
    with image.convert("L") as gray:
        with gray.resize((24, 24), Image.Resampling.BOX) as sample:
            pixels = tuple(sample.tobytes())
    mean = sum(pixels) / len(pixels)
    width = height = 24
    ranked: list[tuple[float, float, int, int]] = []
    for y in range(height):
        for x in range(width):
            index = y * width + x
            value = pixels[index]
            contrast = abs(value - mean)
            if x:
                contrast += abs(value - pixels[index - 1])
            if x + 1 < width:
                contrast += abs(value - pixels[index + 1])
            if y:
                contrast += abs(value - pixels[index - width])
            if y + 1 < height:
                contrast += abs(value - pixels[index + width])
            distance = (x + 0.5 - width / 2.0) ** 2 + (y + 0.5 - height / 2.0) ** 2
            ranked.append((-contrast, distance, y, x))
    _, _, best_y, best_x = min(ranked)
    return ((best_x + 0.5) / width, (best_y + 0.5) / height)


def _clamped_focus(
    image: Image.Image,
    preferred_focus: tuple[float, float] | None,
) -> tuple[float, float]:
    fallback = _visual_center(image)
    if preferred_focus is None:
        return fallback
    try:
        values = (float(preferred_focus[0]), float(preferred_focus[1]))
    except (IndexError, TypeError, ValueError):
        return fallback
    return tuple(
        fallback[index] if not math.isfinite(value) else min(1.0, max(0.0, value))
        for index, value in enumerate(values)
    )  # type: ignore[return-value]


def _protection_interval(face: FaceBox, crop_size: float, axis: str) -> tuple[float, float]:
    start = face.x if axis == "x" else face.y
    size = face.width if axis == "x" else face.height
    inset = crop_size * SAFE_INSET
    return (start + size - crop_size + inset, start - inset)


def _is_protected(face: FaceBox, crop: CropRect) -> bool:
    inset_x = crop.width * SAFE_INSET
    inset_y = crop.height * SAFE_INSET
    return (
        face.x >= crop.x + inset_x - _EPSILON
        and face.x + face.width <= crop.x + crop.width - inset_x + _EPSILON
        and face.y >= crop.y + inset_y - _EPSILON
        and face.y + face.height <= crop.y + crop.height - inset_y + _EPSILON
    )


def _best_crop(
    crop_width: float,
    crop_height: float,
    focus: tuple[float, float],
    faces: tuple[FaceBox, ...],
) -> tuple[CropRect, int]:
    max_x = max(0.0, 1.0 - crop_width)
    max_y = max(0.0, 1.0 - crop_height)
    ideal_x = min(max_x, max(0.0, focus[0] - crop_width / 2.0))
    ideal_y = min(max_y, max(0.0, focus[1] - crop_height / 2.0))
    candidates_x = {0.0, max_x, ideal_x}
    candidates_y = {0.0, max_y, ideal_y}
    for face in faces:
        for value in _protection_interval(face, crop_width, "x"):
            candidates_x.add(min(max_x, max(0.0, value)))
        for value in _protection_interval(face, crop_height, "y"):
            candidates_y.add(min(max_y, max(0.0, value)))

    best: tuple[tuple[float, float, float, float], CropRect, int] | None = None
    for x in sorted(candidates_x):
        for y in sorted(candidates_y):
            crop = CropRect(x, y, crop_width, crop_height)
            protected = sum(_is_protected(face, crop) for face in faces)
            distance = ((x - ideal_x) / crop_width) ** 2 + ((y - ideal_y) / crop_height) ** 2
            rank = (-float(protected), distance, x, y)
            if best is None or rank < best[0]:
                best = (rank, crop, protected)
    assert best is not None
    return (best[1], best[2])


def _render_crop(image: Image.Image, crop: CropRect, target_size: tuple[int, int]) -> Image.Image:
    box = (
        crop.x * image.width,
        crop.y * image.height,
        (crop.x + crop.width) * image.width,
        (crop.y + crop.height) * image.height,
    )
    return image.transform(
        target_size,
        Image.Transform.EXTENT,
        box,
        Image.Resampling.BICUBIC,
    )


def frame_for_mask(
    image: Image.Image,
    target_size: tuple[int, int],
    preferred_focus: tuple[float, float] | None,
    detector: FaceDetector = detect_faces,
) -> FrameResult:
    """Recorte ``image`` para preencher ``target_size`` protegendo rostos confiáveis."""
    image = _validate_image(image)
    if (
        not isinstance(target_size, tuple)
        or len(target_size) != 2
        or any(type(value) is not int or value <= 0 for value in target_size)
    ):
        raise ValueError("O tamanho alvo deve conter largura e altura inteiras maiores que zero.")

    detected = tuple(detector(image))
    if any(not isinstance(face, FaceBox) for face in detected):
        raise ValueError("O detector deve retornar caixas de rosto normalizadas válidas.")
    confident = tuple(face for face in detected if face.confidence >= MIN_FACE_CONFIDENCE)
    crop_width, crop_height = _crop_dimensions(image.size, target_size)
    focus = _clamped_focus(image, preferred_focus)
    crop, protected = _best_crop(crop_width, crop_height, focus, confident)
    framed = _render_crop(image, crop, target_size)
    return FrameResult(
        image=framed,
        crop=crop,
        face_boxes=detected,
        faces_protected=protected,
        safe=protected == len(confident),
    )
