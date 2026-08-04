"""Cached page thumbnails rendered from the exact same PDF page implementation."""

from __future__ import annotations

from collections.abc import Mapping

import pymupdf
from PIL import Image

from .documento import Documento, Tipografia
from .modelos import BookPlan
from .templates import catalog


_CACHE: dict[tuple[int, int, str, int], Image.Image] = {}


def render_page_thumbnail(
    plan: BookPlan,
    page_number: int,
    assets: Mapping[str, object],
    width: int,
) -> Image.Image:
    """Rasterize one planned internal page, cached by the stable plan coordinates."""
    if width <= 0:
        raise ValueError("Thumbnail width must be positive")
    key = (plan.seed, page_number, plan.mode, width)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    try:
        page_plan = next(page for page in plan.pages if page.number == page_number)
    except StopIteration as exc:
        raise ValueError(f"Unknown page number: {page_number}") from exc
    try:
        template = next(item for item in catalog() if item.id == page_plan.template_id)
    except StopIteration as exc:
        raise ValueError(f"Unknown template: {page_plan.template_id}") from exc

    document = Documento("", "", True, Tipografia(), None, modo=plan.mode)
    try:
        page = document.render_page(page_plan, template.resolve(plan.mode), assets)
        scale = width / page.rect.width
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        thumbnail = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    finally:
        document.fechar()
    _CACHE[key] = thumbnail
    return thumbnail


def clear_cache() -> None:
    _CACHE.clear()
