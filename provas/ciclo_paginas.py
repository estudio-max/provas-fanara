"""Deterministic, side-effect-free alternatives for an internal page layout."""

from __future__ import annotations

from collections import Counter
from hashlib import blake2b
from itertools import permutations
from math import log
from typing import Mapping

from .modelos import BookPlan, PagePlan, Template
from .templates import catalog as catalogo


def _pagina_interna(plan: BookPlan, page_number: int) -> tuple[int, PagePlan]:
    if page_number == 0:
        raise ValueError("A capa não possui alternativas de diagramação.")
    for index, page in enumerate(plan.pages):
        if page.number == page_number:
            if page.role == "cover":
                raise ValueError("A capa não possui alternativas de diagramação.")
            return index, page
    raise ValueError(f"Página {page_number} não encontrada no plano.")


def _ratios_da_pagina(page: PagePlan, aspect_ratios: Mapping[str, float]) -> dict[str, float]:
    ratios: dict[str, float] = {}
    for photo_id in page.photo_ids:
        if photo_id not in aspect_ratios:
            raise ValueError(f"Proporção ausente para a foto: {photo_id}")
        ratio = aspect_ratios[photo_id]
        if not isinstance(ratio, (int, float)) or ratio <= 0:
            raise ValueError(f"Proporção inválida para a foto: {photo_id}")
        ratios[photo_id] = float(ratio)
    return ratios


def _orientacao(ratios: Mapping[str, float]) -> str:
    kinds = {
        "portrait" if ratio < 1 else "landscape" if ratio > 1 else "square"
        for ratio in ratios.values()
    }
    return next(iter(kinds)) if len(kinds) == 1 else "mixed"


def _hash_estavel(seed: int, page_number: int, template_id: str, photo_ids: tuple[str, ...]) -> str:
    payload = f"{seed}|{page_number}|{template_id}|{'|'.join(photo_ids)}"
    return blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def _limite_denso_violado(plan: BookPlan, page_index: int, candidate: Template, templates: Mapping[str, Template]) -> bool:
    if candidate.density_class != "dense":
        return False

    before = 0
    for page in reversed(plan.pages[:page_index]):
        template = templates.get(page.template_id)
        if template is None or template.density_class != "dense":
            break
        before += 1

    after = 0
    for page in plan.pages[page_index + 1 :]:
        template = templates.get(page.template_id)
        if template is None or template.density_class != "dense":
            break
        after += 1
    return before + 1 + after > 2


def _templates_compativeis(
    plan: BookPlan,
    page_index: int,
    page: PagePlan,
    orientation: str,
    templates: Mapping[str, Template],
) -> tuple[Template, ...]:
    neighbor_ids = {
        candidate.template_id
        for candidate in (plan.pages[page_index - 1] if page_index else None,
                          plan.pages[page_index + 1] if page_index + 1 < len(plan.pages) else None)
        if candidate is not None
    }
    return tuple(
        template
        for template in templates.values()
        if len(template.slots) == len(page.photo_ids)
        and orientation in template.orientations
        and template.id not in neighbor_ids
        and not _limite_denso_violado(plan, page_index, template, templates)
    )


def _custo_de_enquadramento(template: Template, photo_ids: tuple[str, ...], ratios: Mapping[str, float]) -> float:
    return sum(
        abs(log(ratios[photo_id]) - log(slot.rect.width / slot.rect.height))
        for photo_id, slot in zip(photo_ids, template.slots)
    )


def _melhor_permutacao(
    plan: BookPlan, page: PagePlan, template: Template, ratios: Mapping[str, float]
) -> tuple[str, ...]:
    candidates = tuple(sorted(set(permutations(page.photo_ids))))
    return min(
        candidates,
        key=lambda photo_ids: (
            _custo_de_enquadramento(template, photo_ids, ratios),
            _hash_estavel(plan.seed, page.number, template.id, photo_ids),
        ),
    )


def _adequacao_editorial(
    plan: BookPlan, page_index: int, page: PagePlan, template: Template, templates: Mapping[str, Template]) -> tuple[float, int]:
    neighbor_densities = [
        neighbor_template.density_class
        for neighbor in (plan.pages[page_index - 1] if page_index else None,
                         plan.pages[page_index + 1] if page_index + 1 < len(plan.pages) else None)
        if neighbor is not None
        if (neighbor_template := templates.get(neighbor.template_id)) is not None
    ]
    dominant_density = None
    if neighbor_densities:
        counts = Counter(neighbor_densities)
        dominant_density = min(counts, key=lambda density: (-counts[density], density))

    if page.role in {"opening", "ending"}:
        return (-template.hierarchy_weight, 0)
    density_repeat = int(
        page.role in {"sequence", "narrative"} and template.density_class == dominant_density
    )
    return (0.0, density_repeat)


def alternativas_da_pagina(
    plan: BookPlan, page_number: int, aspect_ratios: Mapping[str, float]
) -> tuple[PagePlan, ...]:
    """Return the finite, repeat-free sequence of compatible page states."""
    page_index, page = _pagina_interna(plan, page_number)
    ratios = _ratios_da_pagina(page, aspect_ratios)
    templates = {template.id: template for template in catalogo()}
    compatible = _templates_compativeis(plan, page_index, page, _orientacao(ratios), templates)

    alternatives: dict[tuple[str, tuple[str, ...]], PagePlan] = {}
    for template in compatible:
        photo_ids = _melhor_permutacao(plan, page, template, ratios)
        candidate = PagePlan(page.number, template.id, photo_ids, page.role)
        alternatives[(candidate.template_id, candidate.photo_ids)] = candidate

    if page.template_id in {template.id for template in compatible}:
        alternatives[(page.template_id, page.photo_ids)] = page

    return tuple(
        sorted(
            alternatives.values(),
            key=lambda candidate: (
                _adequacao_editorial(plan, page_index, page, templates[candidate.template_id], templates),
                _hash_estavel(plan.seed, candidate.number, candidate.template_id, candidate.photo_ids),
            ),
        )
    )


def tem_alternativa(plan: BookPlan, page_number: int, aspect_ratios: Mapping[str, float]) -> bool:
    """Return whether the internal page has at least two different cycle states."""
    alternatives = alternativas_da_pagina(plan, page_number, aspect_ratios)
    return len({(page.template_id, page.photo_ids) for page in alternatives}) >= 2


def ciclar_pagina(plan: BookPlan, page_number: int, aspect_ratios: Mapping[str, float]) -> BookPlan:
    """Return a new plan with only the requested internal page advanced one step."""
    page_index, current = _pagina_interna(plan, page_number)
    alternatives = alternativas_da_pagina(plan, page_number, aspect_ratios)
    if not alternatives:
        return plan

    try:
        next_page = alternatives[(alternatives.index(current) + 1) % len(alternatives)]
    except ValueError:
        next_page = alternatives[0]
    pages = (*plan.pages[:page_index], next_page, *plan.pages[page_index + 1 :])
    return BookPlan(plan.seed, plan.mode, plan.cover_photo_ids, pages)
