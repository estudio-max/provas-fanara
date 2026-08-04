"""Seeded assembly of narrative groups into immutable editorial book plans."""
from __future__ import annotations

from collections import Counter
import random
from typing import Iterable

from .modelos import BookPlan, PagePlan, PhotoInfo, Template
from .narrativa import PhotoGroup, agrupar_fotos
from .templates import catalog, compatible_templates


_MODES = frozenset({"prova", "fotolivro"})


def _ordered(photos: Iterable[PhotoInfo]) -> list[PhotoInfo]:
    items = sorted(photos, key=lambda photo: (photo.index, photo.id))
    if len({photo.id for photo in items}) != len(items):
        raise ValueError("Photo ids must be unique")
    return items


def _orientation_for_ids(photo_ids: Iterable[str], by_id: dict[str, PhotoInfo]) -> str:
    kinds = {
        "portrait" if by_id[photo_id].height > by_id[photo_id].width
        else "landscape" if by_id[photo_id].width > by_id[photo_id].height
        else "square"
        for photo_id in photo_ids
    }
    return next(iter(kinds)) if len(kinds) == 1 else "mixed"


def _orientation(group: PhotoGroup, by_id: dict[str, PhotoInfo]) -> str:
    return _orientation_for_ids(group.photo_ids, by_id)


def _template_candidates(group: PhotoGroup, by_id: dict[str, PhotoInfo], previous_id: str | None) -> tuple[Template, ...]:
    descriptor = type("GroupOrientation", (), {"orientation": _orientation(group, by_id)})()
    candidates = tuple(
        template for template in compatible_templates(descriptor, previous_id)
        if len(template.slots) == len(group.photo_ids)
    )
    return candidates


def _template_weight(template: Template, group: PhotoGroup, recent: tuple[str, ...]) -> float:
    density = 2.2 if template.density_class == group.density else 0.45
    role = template.hierarchy_weight * (1.8 if group.role in {"opening", "ending"} else 0.75)
    recency = sum(0.35 / (position + 1) for position, template_id in enumerate(reversed(recent)) if template_id == template.id)
    return max(0.05, density + role - recency)


def selecionar_capa(photos: Iterable[PhotoInfo], quantidade: int, manual_ids: Iterable[str] = ()) -> tuple[str, ...]:
    """Choose a stable, varied, session-wide set of cover image ids.

    Manual ids take priority and retain their supplied order.  Automatic picks
    are made near evenly-spaced positions, then ranked by image quality and
    similarity-group diversity.
    """
    items = _ordered(photos)
    by_id = {photo.id: photo for photo in items}
    selected: list[str] = []
    for photo_id in manual_ids:
        if photo_id in by_id and photo_id not in selected:
            selected.append(photo_id)
    if len(selected) > 12:
        raise ValueError("A cover supports at most 12 manual ids")
    if len(items) <= 5:
        selected.extend(photo.id for photo in items if photo.id not in selected)
        return tuple(selected)

    target = min(len(items), max(6, min(12, quantidade)))
    target = max(target, len(selected))
    if len(selected) >= target:
        return tuple(selected)

    seen_groups = {by_id[photo_id].similarity_group for photo_id in selected}
    source_span = max(1, target - 1)
    for position in range(target):
        if len(selected) >= target:
            break
        target_index = round(position * (len(items) - 1) / source_span)
        candidates = [photo for photo in items if photo.id not in selected]

        def value(photo: PhotoInfo) -> tuple[float, int, str]:
            diversity = 0.55 if photo.similarity_group not in seen_groups else -0.35
            quality = photo.quality * 0.60 + photo.sharpness * 0.18 + photo.exposure * 0.14 + photo.density * 0.08
            distance = abs(photo.index - target_index) / max(1, len(items) - 1)
            return (quality + diversity - distance * 2.0, -photo.index, photo.id)

        chosen = max(candidates, key=value)
        selected.append(chosen.id)
        seen_groups.add(chosen.similarity_group)
    return tuple(selected)


def validate_plan(plan: BookPlan, photos: Iterable[PhotoInfo]) -> tuple[str, ...]:
    """Return all user-actionable invariant violations in a book plan."""
    errors: list[str] = []
    items = list(photos)
    source_ids = [photo.id for photo in items]
    source_set = set(source_ids)
    by_id = {photo.id: photo for photo in items}
    templates = {template.id: template for template in catalog()}
    if plan.mode not in _MODES:
        errors.append(f"Unsupported mode: {plan.mode}")
    if len(source_set) != len(source_ids):
        errors.append("Source photo ids must be unique")
    page_ids = [photo_id for page in plan.pages for photo_id in page.photo_ids]
    if Counter(page_ids) != Counter(source_ids):
        errors.append("Every source photo must appear exactly once")
    if any(photo_id not in source_set for photo_id in plan.cover_photo_ids):
        errors.append("Cover ids must reference source photos")
    if len(set(plan.cover_photo_ids)) != len(plan.cover_photo_ids):
        errors.append("Cover ids must be unique")

    dense_run = 0
    for expected_number, page in enumerate(plan.pages, start=1):
        template = templates.get(page.template_id)
        if page.number != expected_number:
            errors.append("Page numbers must be consecutive")
        if template is None:
            errors.append(f"Unknown template: {page.template_id}")
            dense_run = 0
            continue
        if len(template.slots) != len(page.photo_ids):
            errors.append(f"Template {template.id} has an incompatible photo count")
        elif all(photo_id in by_id for photo_id in page.photo_ids):
            orientation = _orientation_for_ids(page.photo_ids, by_id)
            if orientation not in template.orientations:
                errors.append(f"Template {template.id} has incompatible {orientation} orientation")
        dense_run = dense_run + 1 if template.density_class == "dense" else 0
        if dense_run > 2:
            errors.append("No more than two dense pages may be adjacent")
    if any(left.template_id == right.template_id for left, right in zip(plan.pages, plan.pages[1:])):
        errors.append("Neighboring pages cannot repeat a template")
    if plan.pages:
        if plan.pages[0].role != "opening":
            errors.append("First page must have the opening role")
        if len(plan.pages) > 1:
            if plan.pages[-1].role != "ending":
                errors.append("Last page must have the ending role")
            if plan.pages[0].role == plan.pages[-1].role:
                errors.append("Opening and ending roles must be distinct")
    return tuple(errors)


def compose(photos: Iterable[PhotoInfo], mode: str, seed: int, cover_ids: Iterable[str] = ()) -> BookPlan:
    """Build a deterministic plan from all valid photos exactly once."""
    if mode not in _MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    items = _ordered(photos)
    by_id = {photo.id: photo for photo in items}
    rng = random.Random(seed)
    pages: list[PagePlan] = []
    recent: tuple[str, ...] = ()
    previous_id: str | None = None
    for number, group in enumerate(agrupar_fotos(items, seed), start=1):
        candidates = _template_candidates(group, by_id, previous_id)
        if not candidates:
            raise ValueError(f"No compatible template for {len(group.photo_ids)} photos")
        weights = [_template_weight(template, group, recent) for template in candidates]
        selected = rng.choices(candidates, weights=weights, k=1)[0]
        pages.append(PagePlan(number, selected.id, group.photo_ids, group.role))
        previous_id = selected.id
        recent = (*recent[-2:], selected.id)

    plan = BookPlan(seed, mode, selecionar_capa(items, quantidade=9, manual_ids=cover_ids), tuple(pages))
    errors = validate_plan(plan, items)
    if errors:
        raise ValueError("; ".join(errors))
    return plan
