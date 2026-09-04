from __future__ import annotations

from dataclasses import replace

import pytest

from provas.modelos import PhotoInfo


def _photos(total: int = 17) -> list[PhotoInfo]:
    return [
        PhotoInfo(
            id=f"p{index}", path=f"p{index}.jpg", label=f"P {index}",
            width=300 if index % 3 else 180, height=180 if index % 3 else 300,
            index=index, sharpness=(index % 5) / 4, exposure=0.35 + (index % 4) / 6,
            density=(index % 4) / 3, quality=(total - index) / total,
            similarity_group=index // 2,
        )
        for index in range(total)
    ]


def test_compose_is_deterministic_and_covers_each_photo_once():
    from provas.compositor import compose, validate_plan

    photos = _photos()
    first = compose(photos, mode="fotolivro", seed=71)
    second = compose(photos, mode="fotolivro", seed=71)

    assert first == second
    assert validate_plan(first, photos) == ()
    assert sorted(photo_id for page in first.pages for photo_id in page.photo_ids) == sorted(photo.id for photo in photos)
    assert all(len(page.photo_ids) in {1, 2, 4} for page in first.pages)


def test_compose_varies_seed_without_breaking_editorial_invariants():
    from provas.compositor import compose, validate_plan
    from provas.templates import catalog

    photos = _photos(31)
    plans = [compose(photos, mode="prova", seed=seed) for seed in range(5)]
    templates = {template.id: template for template in catalog()}

    assert len(set(plans)) > 1
    for plan in plans:
        assert validate_plan(plan, photos) == ()
        assert all(left.template_id != right.template_id for left, right in zip(plan.pages, plan.pages[1:]))
        dense_run = longest_run = 0
        for page in plan.pages:
            dense_run = dense_run + 1 if templates[page.template_id].density_class == "dense" else 0
            longest_run = max(longest_run, dense_run)
        assert longest_run <= 2
        assert plan.pages[0].role == "opening"
        assert plan.pages[-1].role == "ending"
        assert plan.pages[0].photo_ids != plan.pages[-1].photo_ids


def test_compose_rejects_unknown_mode_and_duplicate_source_ids():
    from provas.compositor import compose

    photos = _photos(4)
    with pytest.raises(ValueError, match="Unsupported mode"):
        compose(photos, mode="draft", seed=1)
    with pytest.raises(ValueError, match="unique"):
        compose(photos + [replace(photos[0], index=9)], mode="prova", seed=1)


def test_compose_allows_a_single_photo_as_an_opening_page():
    from provas.compositor import compose, validate_plan

    plan = compose(_photos(1), mode="prova", seed=1)

    assert plan.pages[0].role == "opening"
    assert validate_plan(plan, _photos(1)) == ()


def test_validate_plan_reports_broken_invariants_without_repairing_input():
    from provas.compositor import compose, validate_plan
    from provas.modelos import BookPlan, PagePlan

    photos = _photos(5)
    plan = compose(photos, mode="prova", seed=2)
    invalid = BookPlan(
        plan.seed, plan.mode, plan.cover_photo_ids,
        (PagePlan(1, "single-full", ("p0",), "opening"), PagePlan(2, "single-full", ("p0",), "ending")),
    )

    errors = validate_plan(invalid, photos)

    assert any("exactly once" in error for error in errors)
    assert any("repeat" in error for error in errors)


def test_validate_plan_reports_an_invalid_mode_directly():
    from provas.compositor import validate_plan
    from provas.modelos import BookPlan

    errors = validate_plan(BookPlan(3, "rascunho", (), ()), ())

    assert errors == ("Unsupported mode: rascunho",)


def test_validate_plan_reports_template_orientation_incompatibility():
    from provas.compositor import validate_plan
    from provas.modelos import BookPlan, PagePlan

    squares = [
        PhotoInfo("s0", "s0.jpg", "S 0", 200, 200, 0),
        PhotoInfo("s1", "s1.jpg", "S 1", 200, 200, 1),
    ]
    plan = BookPlan(3, "prova", (), (PagePlan(1, "pair-portraits", ("s0", "s1"), "opening"),))

    errors = validate_plan(plan, squares)

    assert any("orientation" in error for error in errors)


def test_template_candidates_keep_square_and_mixed_groups_orientation_compatible():
    from provas.compositor import _template_candidates
    from provas.narrativa import PhotoGroup

    items = {
        "s0": PhotoInfo("s0", "s0.jpg", "S 0", 200, 200, 0),
        "s1": PhotoInfo("s1", "s1.jpg", "S 1", 200, 200, 1),
        "p": PhotoInfo("p", "p.jpg", "P", 200, 300, 2),
        "l": PhotoInfo("l", "l.jpg", "L", 300, 200, 3),
    }

    square_candidates = _template_candidates(PhotoGroup(("s0", "s1"), "sequence", "balanced"), items, None)
    mixed_candidates = _template_candidates(PhotoGroup(("p", "l"), "sequence", "balanced"), items, None)
    exhausted_square = _template_candidates(PhotoGroup(("s0", "s1"), "sequence", "balanced"), items, "pair-squares")

    assert square_candidates and all("square" in template.orientations for template in square_candidates)
    assert mixed_candidates and all("mixed" in template.orientations for template in mixed_candidates)
    assert exhausted_square == ()


def test_compose_uses_only_square_templates_for_a_square_narrative():
    from provas.compositor import compose, validate_plan
    from provas.templates import catalog

    squares = [PhotoInfo(f"s{index}", f"s{index}.jpg", f"S {index}", 200, 200, index) for index in range(5)]
    plan = compose(squares, mode="prova", seed=5)
    templates = {template.id: template for template in catalog()}

    assert validate_plan(plan, squares) == ()
    assert all("square" in templates[page.template_id].orientations for page in plan.pages)


def test_cover_selection_keeps_manual_ids_in_order_and_is_stable():
    from provas.compositor import selecionar_capa

    photos = _photos(20)
    manual = ("p13", "p2", "missing", "p13")

    selected = selecionar_capa(photos, quantidade=9, manual_ids=manual)

    assert selected == selecionar_capa(photos, quantidade=9, manual_ids=manual)
    assert selected[:2] == ("p13", "p2")
    assert len(selected) == len(set(selected)) == 9
    assert all(photo_id in {photo.id for photo in photos} for photo_id in selected)


def test_cover_selection_rejects_more_than_twelve_valid_manual_ids():
    from provas.compositor import selecionar_capa

    photos = _photos(20)

    with pytest.raises(ValueError, match="at most 12"):
        selecionar_capa(photos, quantidade=9, manual_ids=tuple(photo.id for photo in photos[:13]))


def test_cover_selection_diversifies_groups_and_source_sequence():
    from provas.compositor import selecionar_capa

    photos = _photos(24)
    selected = selecionar_capa(photos, quantidade=9)
    by_id = {photo.id: photo for photo in photos}
    groups = [by_id[photo_id].similarity_group for photo_id in selected]
    positions = sorted(by_id[photo_id].index for photo_id in selected)

    assert len(selected) == 9
    assert len(set(groups)) >= 6
    assert positions[0] <= 2 and positions[-1] >= 21
    assert max(right - left for left, right in zip(positions, positions[1:])) <= 6


@pytest.mark.parametrize("total", [0, 1, 4, 5])
def test_cover_selection_uses_each_available_photo_once_for_small_folders(total):
    from provas.compositor import selecionar_capa

    photos = _photos(total)

    assert selecionar_capa(photos, quantidade=9) == tuple(photo.id for photo in photos)


def test_small_folder_cover_selection_keeps_manual_order_without_duplicates():
    from provas.compositor import selecionar_capa

    selected = selecionar_capa(_photos(4), quantidade=9, manual_ids=("p3", "p1", "p3"))

    assert selected[:2] == ("p3", "p1")
    assert set(selected) == {"p0", "p1", "p2", "p3"}
    assert len(selected) == 4
