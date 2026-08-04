from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from provas.capa_curvas import (
    ORBIT_VARIANTS,
    CurveLayout,
    CurveSlot,
    PixelRect,
    layout_orbita,
    render_mask,
)


def _opaque_coverage(slot: CurveSlot, size: tuple[int, int]) -> float:
    mask = render_mask(slot, size)
    intensity = sum(mask.get_flattened_data())
    return round(intensity / (255 * slot.bounds.area), 4)


def _snapshot(layout: CurveLayout, size: tuple[int, int]):
    return tuple(
        (
            slot.id,
            (slot.bounds.x, slot.bounds.y, slot.bounds.width, slot.bounds.height),
            _opaque_coverage(slot, size),
        )
        for slot in layout.slots
    )


def test_pixel_rect_reports_edges_area_and_intersection():
    rect = PixelRect(10, 20, 40, 30)

    assert (rect.right, rect.bottom, rect.area) == (50, 50, 1200)
    assert rect.intersection(PixelRect(30, 5, 40, 30)) == PixelRect(30, 20, 20, 15)
    assert rect.intersection(PixelRect(80, 80, 5, 5)).area == 0


@pytest.mark.parametrize("count", range(1, 10))
def test_orbit_layout_has_one_visible_slot_per_photo_and_safe_regions(count):
    width, height = 1600, 1131
    layout = layout_orbita(width, height, count)
    canvas = PixelRect(0, 0, width, height)

    assert len(layout.slots) == count
    assert len({slot.id for slot in layout.slots}) == count
    assert all(slot.bounds.area > 0 for slot in layout.slots)
    assert all(slot.bounds.intersection(canvas) == slot.bounds for slot in layout.slots)
    assert all(slot.bounds.intersection(layout.identity_safe_rect).area == 0 for slot in layout.slots)
    assert layout.logo_rect.intersection(canvas) == layout.logo_rect
    assert layout.site_rect.intersection(canvas) == layout.site_rect


@pytest.mark.parametrize("count", range(6, 10))
def test_dense_variants_keep_the_exact_central_identity_region(count):
    assert layout_orbita(1600, 1131, count).identity_safe_rect == PixelRect(608, 385, 384, 339)


def test_orbit_variants_are_immutable_and_indexed_one_through_nine():
    assert tuple(ORBIT_VARIANTS) == tuple(range(1, 10))
    assert all(len(ORBIT_VARIANTS[count]) == count for count in range(1, 10))

    with pytest.raises(TypeError):
        ORBIT_VARIANTS[1] = ()  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        ORBIT_VARIANTS[1][0].id = "alterado"  # type: ignore[misc]


@pytest.mark.parametrize(
    "width,height,count",
    [
        (0, 1131, 1),
        (1600, 0, 1),
        (1131, 1600, 1),
        (1000, 1000, 1),
        (1600, 1131, 0),
        (1600, 1131, 10),
    ],
)
def test_orbit_rejects_invalid_canvas_or_photo_count_in_portuguese(width, height, count):
    with pytest.raises(ValueError, match="A órbita exige.*1 a 9 fotografias"):
        layout_orbita(width, height, count)


@pytest.mark.parametrize("size", [(2, 1), (3, 2), (15, 11), (16, 10)])
def test_orbit_rejects_canvas_too_small_for_visible_slots(size):
    with pytest.raises(ValueError, match="A órbita exige no mínimo 16×11 pixels"):
        layout_orbita(*size, 9)


def test_minimum_canvas_keeps_every_slot_visible():
    size = (16, 11)

    for count in range(1, 10):
        layout = layout_orbita(*size, count)
        assert all(slot.bounds.area > 0 for slot in layout.slots)
        assert all(render_mask(slot, size).getbbox() is not None for slot in layout.slots)


def test_curve_masks_are_antialiased_non_rectangular_and_byte_deterministic():
    slot = layout_orbita(1600, 1131, 6).slots[0]

    first = render_mask(slot, (1600, 1131))
    second = render_mask(slot, (1600, 1131))
    values = set(first.get_flattened_data())

    assert first.mode == "L"
    assert first.size == (1600, 1131)
    assert first.tobytes() == second.tobytes()
    assert 0 in values
    assert 255 in values
    assert any(0 < value < 255 for value in values)
    assert sum(value == 255 for value in first.get_flattened_data()) < slot.bounds.area * 0.9


@pytest.mark.parametrize("size", [(1600, 1131), (800, 566)])
def test_every_mask_antialias_halo_is_clipped_to_its_pixel_bounds(size):
    for count in range(1, 10):
        for slot in layout_orbita(*size, count).slots:
            bbox = render_mask(slot, size).getbbox()
            assert bbox is not None
            assert slot.bounds.x <= bbox[0]
            assert slot.bounds.y <= bbox[1]
            assert bbox[2] <= slot.bounds.right
            assert bbox[3] <= slot.bounds.bottom


def test_representative_a4_geometry_snapshot():
    assert _snapshot(layout_orbita(1600, 1131, 6), (1600, 1131)) == (
        ("upper_left", (48, 34, 704, 305), 0.7834),
        ("upper_right", (848, 34, 704, 305), 0.7834),
        ("side_left", (32, 317, 528, 463), 0.7840),
        ("side_right", (1040, 317, 528, 463), 0.7839),
        ("lower_left", (48, 792, 704, 305), 0.7835),
        ("lower_right", (848, 792, 704, 305), 0.7834),
    )


def test_nine_photo_and_smaller_proportional_geometry_snapshots():
    assert _snapshot(layout_orbita(1600, 1131, 9), (1600, 1131)) == (
        ("upper_left", (48, 34, 464, 305), 0.7838),
        ("upper_center", (568, 23, 464, 316), 0.7844),
        ("upper_right", (1088, 34, 464, 305), 0.7837),
        ("side_left", (32, 317, 528, 463), 0.7840),
        ("side_right", (1040, 317, 528, 463), 0.7839),
        ("lower_left", (32, 792, 368, 305), 0.7839),
        ("lower_center_left", (424, 792, 360, 305), 0.7839),
        ("lower_center_right", (816, 792, 360, 305), 0.7840),
        ("lower_right", (1200, 792, 368, 305), 0.7839),
    )
    assert _snapshot(layout_orbita(800, 566, 6), (800, 566)) == (
        ("upper_left", (24, 17, 352, 153), 0.7820),
        ("upper_right", (424, 17, 352, 153), 0.7820),
        ("side_left", (16, 158, 264, 233), 0.7803),
        ("side_right", (520, 158, 264, 233), 0.7803),
        ("lower_left", (24, 396, 352, 153), 0.7820),
        ("lower_right", (424, 396, 352, 153), 0.7819),
    )


def test_coverage_snapshot_detects_a_substantial_silhouette_mutation():
    size = (1600, 1131)
    slot = layout_orbita(*size, 6).slots[0]
    left = slot.bounds.x / size[0]
    top = slot.bounds.y / size[1]
    right = slot.bounds.right / size[0]
    bottom = slot.bounds.bottom / size[1]
    rectangular_mutant = CurveSlot(
        slot.id,
        ((left, top), (right, top), (right, bottom), (left, bottom)),
        slot.bounds,
        slot.preferred_focus,
    )

    assert _opaque_coverage(rectangular_mutant, size) - _opaque_coverage(slot, size) > 0.15
