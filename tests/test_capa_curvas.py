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


def _opaque_ratio(slot: CurveSlot, size: tuple[int, int]) -> float:
    mask = render_mask(slot, size)
    opaque = sum(value == 255 for value in mask.get_flattened_data())
    return round(opaque / slot.bounds.area, 1)


def _snapshot(layout: CurveLayout, size: tuple[int, int]):
    return tuple(
        (
            slot.id,
            (slot.bounds.x, slot.bounds.y, slot.bounds.width, slot.bounds.height),
            _opaque_ratio(slot, size),
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


def test_representative_a4_geometry_snapshot():
    assert _snapshot(layout_orbita(1600, 1131, 6), (1600, 1131)) == (
        ("upper_left", (48, 34, 704, 305), 0.8),
        ("upper_right", (848, 34, 704, 305), 0.8),
        ("side_left", (32, 317, 528, 463), 0.8),
        ("side_right", (1040, 317, 528, 463), 0.8),
        ("lower_left", (48, 792, 704, 305), 0.8),
        ("lower_right", (848, 792, 704, 305), 0.8),
    )


def test_nine_photo_and_smaller_proportional_geometry_snapshots():
    assert _snapshot(layout_orbita(1600, 1131, 9), (1600, 1131)) == (
        ("upper_left", (48, 34, 464, 305), 0.8),
        ("upper_center", (568, 23, 464, 316), 0.8),
        ("upper_right", (1088, 34, 464, 305), 0.8),
        ("side_left", (32, 317, 528, 463), 0.8),
        ("side_right", (1040, 317, 528, 463), 0.8),
        ("lower_left", (32, 792, 368, 305), 0.8),
        ("lower_center_left", (424, 792, 360, 305), 0.8),
        ("lower_center_right", (816, 792, 360, 305), 0.8),
        ("lower_right", (1200, 792, 368, 305), 0.8),
    )
    assert _snapshot(layout_orbita(800, 566, 6), (800, 566)) == (
        ("upper_left", (24, 17, 352, 153), 0.8),
        ("upper_right", (424, 17, 352, 153), 0.8),
        ("side_left", (16, 158, 264, 233), 0.8),
        ("side_right", (520, 158, 264, 233), 0.8),
        ("lower_left", (24, 396, 352, 153), 0.8),
        ("lower_right", (424, 396, 352, 153), 0.8),
    )
