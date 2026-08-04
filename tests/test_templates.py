from dataclasses import FrozenInstanceError

import pytest

from provas.modelos import BookPlan, PagePlan, PhotoInfo, Rect, Slot, Template
from provas.templates import catalog, compatible_templates, fit_contain


def test_fit_contain_preserves_two_by_three():
    fitted = fit_contain(Rect(0, 0, 300, 180), ratio=1.5)

    assert fitted.width / fitted.height == pytest.approx(1.5)
    assert fitted.x >= 0 and fitted.right <= 300
    assert fitted.y >= 0 and fitted.bottom <= 180
    assert fitted.x == pytest.approx(15)
    assert fitted.y == 0


def test_catalog_only_contains_supported_counts_and_curated_distribution():
    templates = catalog()
    counts = [len(template.slots) for template in templates]

    assert set(counts) <= {1, 2, 4}
    assert len(templates) >= 12
    assert counts.count(1) >= 3
    assert counts.count(2) >= 5
    assert counts.count(4) >= 4


def test_proof_slots_reserve_caption_space():
    template = next(template for template in catalog() if len(template.slots) == 2)

    assert all(slot.caption.height > 0 for slot in template.resolve("prova").slots)


def test_fotolivro_slots_do_not_reserve_caption_space():
    template = next(template for template in catalog() if len(template.slots) == 2)

    assert all(slot.caption.height == 0 for slot in template.resolve("fotolivro").slots)


def test_compatible_templates_require_matching_orientation_and_new_id():
    template = next(template for template in catalog() if len(template.slots) == 1)
    group = type("Group", (), {"orientation": "portrait"})()

    candidates = compatible_templates(group, previous_id=template.id)

    assert template.id not in {candidate.id for candidate in candidates}
    assert all("portrait" in candidate.orientations for candidate in candidates)


def test_compatible_templates_treat_multiple_group_orientations_as_mixed():
    group = type("Group", (), {"orientations": ("portrait", "landscape")})()

    candidates = compatible_templates(group)

    assert candidates
    assert all("mixed" in candidate.orientations for candidate in candidates)


def test_shared_models_are_immutable():
    photo = PhotoInfo("1", "photo.jpg", "Photo", 200, 300, 0)
    page = PagePlan(1, "single-portrait", ("1",), "opening")
    book = BookPlan(7, "prova", (), (page,))

    with pytest.raises(FrozenInstanceError):
        photo.label = "Changed"
    with pytest.raises(FrozenInstanceError):
        page.role = "ending"
    with pytest.raises(FrozenInstanceError):
        book.mode = "fotolivro"


def test_template_copies_mutable_constructor_collections():
    slots = [Slot(Rect(0, 0, 1, 1))]
    orientations = ["portrait"]
    template = Template("custom", slots, orientations, 1.0, "airy")

    slots.clear()
    orientations.append("landscape")

    assert len(template.slots) == 1
    assert template.orientations == frozenset({"portrait"})


def test_page_and_book_plans_copy_mutable_constructor_collections():
    photo_ids = ["1"]
    pages = [PagePlan(1, "single-portrait", photo_ids, "opening")]
    cover_ids = ["1"]
    book = BookPlan(7, "prova", cover_ids, pages)

    photo_ids.append("2")
    cover_ids.append("2")
    pages.clear()

    assert book.cover_photo_ids == ("1",)
    assert book.pages[0].photo_ids == ("1",)
