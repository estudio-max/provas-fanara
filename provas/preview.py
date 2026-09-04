"""Cached page thumbnails rendered from the exact same PDF page implementation."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable, Mapping
from hashlib import sha256
import os

import pymupdf
from PIL import Image

from .documento import Documento, RenderAsset, Tipografia
from .modelos import BookPlan, PhotoInfo
from .templates import catalog


_CACHE_LIMIT = 128
_CACHE: OrderedDict[Hashable, Image.Image] = OrderedDict()


def _plan_fingerprint(plan: BookPlan) -> tuple[object, ...]:
    return (
        plan.seed,
        plan.mode,
        plan.cover_photo_ids,
        tuple(
            (page.number, page.template_id, page.photo_ids, page.role)
            for page in plan.pages
        ),
    )


def _path_fingerprint(path: str) -> tuple[object, ...]:
    absolute = os.path.abspath(path)
    try:
        stat = os.stat(absolute)
        return absolute, stat.st_size, stat.st_mtime_ns
    except OSError:
        return absolute, None, None


def _asset_fingerprint(photo_id: str, source: object) -> tuple[object, ...]:
    if isinstance(source, RenderAsset):
        digest = sha256(source.jpeg).hexdigest()
        return photo_id, source.label, source.width, source.height, digest
    if isinstance(source, PhotoInfo):
        return (
            photo_id, source.label, source.width, source.height,
            _path_fingerprint(source.path),
        )
    if isinstance(source, (bytes, bytearray)):
        return photo_id, sha256(bytes(source)).hexdigest()
    if isinstance(source, Image.Image):
        return photo_id, source.mode, source.size, sha256(source.tobytes()).hexdigest()
    return photo_id, type(source).__qualname__, repr(source)


def _stable_style(value: object) -> Hashable:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _stable_style(item)) for key, item in value.items()))
    if isinstance(value, (tuple, list)):
        return tuple(_stable_style(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_stable_style(item) for item in value))
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value  # type: ignore[return-value]


def render_page_thumbnail(
    plan: BookPlan,
    page_number: int,
    assets: Mapping[str, object],
    width: int,
    *,
    document_factory: Callable[[], Documento] | None = None,
    style_fingerprint: object = (),
) -> Image.Image:
    """Rasterize a planned page with a content-aware, bounded LRU cache."""
    if width <= 0:
        raise ValueError("Thumbnail width must be positive")
    try:
        page_plan = next(page for page in plan.pages if page.number == page_number)
    except StopIteration as exc:
        raise ValueError(f"Unknown page number: {page_number}") from exc
    missing = [photo_id for photo_id in page_plan.photo_ids if photo_id not in assets]
    if missing:
        raise ValueError(f"Missing preview assets: {', '.join(missing)}")
    key = (
        _plan_fingerprint(plan),
        page_number,
        tuple(_asset_fingerprint(photo_id, assets[photo_id]) for photo_id in page_plan.photo_ids),
        _stable_style(style_fingerprint),
        width,
    )
    cached = _CACHE.get(key)
    if cached is not None:
        _CACHE.move_to_end(key)
        return cached

    try:
        template = next(item for item in catalog() if item.id == page_plan.template_id)
    except StopIteration as exc:
        raise ValueError(f"Unknown template: {page_plan.template_id}") from exc

    factory = document_factory or (
        lambda: Documento("", "", True, Tipografia(), None, modo=plan.mode)
    )
    document = factory()
    try:
        page = document.render_page(page_plan, template.resolve(plan.mode), assets)
        scale = width / page.rect.width
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        thumbnail = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    finally:
        document.fechar()
    _CACHE[key] = thumbnail
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_LIMIT:
        _CACHE.popitem(last=False)
    return thumbnail


def clear_cache() -> None:
    _CACHE.clear()
