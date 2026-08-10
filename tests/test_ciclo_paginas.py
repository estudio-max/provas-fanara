from __future__ import annotations

from dataclasses import dataclass

import pytest

from provas.ciclo_paginas import alternativas_da_pagina, ciclar_pagina, tem_alternativa
from provas.modelos import BookPlan, PagePlan, Rect, Slot, Template
from provas.templates import catalog


@dataclass(frozen=True)
class CycleCase:
    name: str
    plan: BookPlan
    page_number: int
    ratios: dict[str, float]

    @property
    def page(self) -> PagePlan:
        return next(page for page in self.plan.pages if page.number == self.page_number)


def _plan(page: PagePlan, *, before: PagePlan | None = None, after: PagePlan | None = None) -> BookPlan:
    pages = tuple(item for item in (before, page, after) if item is not None)
    return BookPlan(731, "fotolivro", (), pages)


@pytest.fixture(
    params=(
        CycleCase(
            "uma_vertical",
            _plan(PagePlan(1, "single-portrait", ("v1",), "opening")),
            1,
            {"v1": 2 / 3},
        ),
        CycleCase(
            "uma_horizontal",
            _plan(PagePlan(1, "single-landscape", ("h1",), "opening")),
            1,
            {"h1": 3 / 2},
        ),
        CycleCase(
            "duas_verticais",
            _plan(PagePlan(1, "pair-asymmetric-left", ("v1", "v2"), "sequence")),
            1,
            {"v1": 2 / 3, "v2": 3 / 4},
        ),
        CycleCase(
            "duas_horizontais",
            _plan(PagePlan(1, "pair-asymmetric-right", ("h1", "h2"), "sequence")),
            1,
            {"h1": 3 / 2, "h2": 4 / 3},
        ),
        CycleCase(
            "duas_mistas",
            _plan(PagePlan(1, "pair-asymmetric-left", ("v1", "h1"), "narrative")),
            1,
            {"v1": 2 / 3, "h1": 3 / 2},
        ),
        CycleCase(
            "quatro_verticais",
            _plan(PagePlan(1, "quad-left-feature", ("v1", "v2", "v3", "v4"), "narrative")),
            1,
            {"v1": 2 / 3, "v2": 3 / 4, "v3": 4 / 5, "v4": 5 / 6},
        ),
        CycleCase(
            "quatro_horizontais",
            _plan(PagePlan(1, "quad-top-feature", ("h1", "h2", "h3", "h4"), "narrative")),
            1,
            {"h1": 3 / 2, "h2": 4 / 3, "h3": 5 / 4, "h4": 6 / 5},
        ),
        CycleCase(
            "quatro_mistas",
            _plan(
                PagePlan(1, "quad-left-feature", ("v1", "h1", "v2", "h2"), "narrative")
            ),
            1,
            {"v1": 2 / 3, "h1": 3 / 2, "v2": 3 / 4, "h2": 4 / 3},
        ),
    ),
    ids=lambda case: case.name,
)
def case(request) -> CycleCase:
    return request.param


def walk_full_cycle(plan: BookPlan, page_number: int, ratios: dict[str, float]) -> tuple[PagePlan, ...]:
    alternatives = alternativas_da_pagina(plan, page_number, ratios)
    assert alternatives
    return alternatives


def test_cycle_keeps_exact_photo_set_and_may_change_order(case: CycleCase):
    states = walk_full_cycle(case.plan, case.page_number, case.ratios)
    expected = sorted(case.page.photo_ids)

    assert all(sorted(state.photo_ids) == expected for state in states)
    if len(expected) > 1:
        assert any(state.photo_ids != case.page.photo_ids for state in states)


def test_cycle_is_deterministic_and_has_no_repeat_before_wrap(case: CycleCase):
    first = alternativas_da_pagina(case.plan, case.page_number, case.ratios)
    second = alternativas_da_pagina(case.plan, case.page_number, case.ratios)

    assert isinstance(first, tuple)
    assert first == second
    assert len(first) == len({(page.template_id, page.photo_ids) for page in first})


def test_cycle_preserves_current_compatible_state_and_advances_from_it(case: CycleCase):
    alternatives = alternativas_da_pagina(case.plan, case.page_number, case.ratios)
    current = case.page

    assert current in alternatives
    if len(alternatives) > 1:
        cycled = ciclar_pagina(case.plan, case.page_number, case.ratios)
        assert next(page for page in cycled.pages if page.number == case.page_number) != current


def test_legacy_template_starts_at_first_known_alternative_and_keeps_other_pages():
    target = PagePlan(2, "template-legado-ausente", ("h1", "h2"), "sequence")
    before = PagePlan(1, "single-portrait", ("v0",), "opening")
    after = PagePlan(3, "single-landscape", ("h3",), "ending")
    plan = _plan(target, before=before, after=after)
    ratios = {"v0": 2 / 3, "h1": 3 / 2, "h2": 4 / 3, "h3": 3 / 2}

    alternatives = alternativas_da_pagina(plan, 2, ratios)
    cycled = ciclar_pagina(plan, 2, ratios)

    assert alternatives
    assert all(page.template_id != target.template_id for page in alternatives)
    assert cycled.pages[0] == before and cycled.pages[2] == after
    assert cycled.pages[1] == alternatives[0]


def test_neighbors_and_dense_run_restrict_compatible_templates():
    target = PagePlan(2, "pair-breathing", ("v1", "h1"), "sequence")
    plan = _plan(
        target,
        before=PagePlan(1, "pair-asymmetric-left", ("v0", "h0"), "opening"),
        after=PagePlan(3, "pair-asymmetric-right", ("v2", "h2"), "ending"),
    )
    ratios = {photo_id: 2 / 3 if photo_id.startswith("v") else 3 / 2 for photo_id in "v0 h0 v1 h1 v2 h2".split()}

    alternatives = alternativas_da_pagina(plan, 2, ratios)

    assert alternatives
    assert {page.template_id for page in alternatives}.isdisjoint(
        {"pair-asymmetric-left", "pair-asymmetric-right"}
    )

    dense_plan = BookPlan(
        731,
        "fotolivro",
        (),
        (
            PagePlan(1, "quad-grid", ("a", "b", "c", "d"), "opening"),
            PagePlan(2, "quad-left-feature", ("e", "f", "g", "h"), "narrative"),
            PagePlan(3, "quad-top-feature", ("i", "j", "k", "l"), "ending"),
        ),
    )
    dense_ratios = {photo_id: 2 / 3 for photo_id in "a b c d e f g h i j k l".split()}
    assert alternativas_da_pagina(dense_plan, 3, dense_ratios) == ()


def test_future_compatible_template_enters_cycle(monkeypatch):
    page = PagePlan(1, "quad-left-feature", ("v1", "h1", "v2", "h2"), "narrative")
    plan = _plan(page)
    ratios = {"v1": 2 / 3, "h1": 3 / 2, "v2": 3 / 4, "h2": 4 / 3}
    future = Template(
        "future_four",
        (
            Slot(Rect(0.05, 0.05, 0.42, 0.42)),
            Slot(Rect(0.53, 0.05, 0.42, 0.42)),
            Slot(Rect(0.05, 0.53, 0.42, 0.42)),
            Slot(Rect(0.53, 0.53, 0.42, 0.42)),
        ),
        {"mixed"},
        0.75,
        "dense",
    )
    monkeypatch.setattr("provas.ciclo_paginas.catalogo", lambda: (*catalog(), future))

    assert "future_four" in {
        candidate.template_id for candidate in alternativas_da_pagina(plan, page.number, ratios)
    }


@pytest.mark.parametrize("page_number", (0, 99))
def test_rejects_cover_and_missing_page_in_portuguese(page_number: int):
    plan = _plan(PagePlan(1, "single-portrait", ("v1",), "opening"))

    with pytest.raises(ValueError, match="(capa|Capa|Página|página)"):
        alternativas_da_pagina(plan, page_number, {"v1": 2 / 3})


def test_rejects_missing_ratio_in_portuguese():
    plan = _plan(PagePlan(1, "pair-portraits", ("v1", "v2"), "opening"))

    with pytest.raises(ValueError, match="(proporção|Proporção)"):
        alternativas_da_pagina(plan, 1, {"v1": 2 / 3})


def test_tem_alternativa_requires_two_distinct_states():
    pair = _plan(PagePlan(1, "pair-asymmetric-left", ("v1", "h1"), "opening"))

    assert tem_alternativa(pair, 1, {"v1": 2 / 3, "h1": 3 / 2})
