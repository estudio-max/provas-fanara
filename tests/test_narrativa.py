from __future__ import annotations

from dataclasses import FrozenInstanceError
import random

import pytest

from provas.modelos import PhotoInfo


def _photos(total: int) -> list[PhotoInfo]:
    return [
        PhotoInfo(
            id=f"p{index}", path=f"p{index}.jpg", label=f"P {index}", width=120, height=180,
            index=index, sharpness=(index % 5) / 4, exposure=0.5, density=(index % 4) / 3,
            quality=(total - index) / total, similarity_group=index // 2,
        )
        for index in range(total)
    ]


@pytest.mark.parametrize("total", [2, 3, 5, 9, 17, 31])
def test_agrupar_fotos_covers_every_photo_once_in_allowed_group_sizes(total):
    from provas.narrativa import agrupar_fotos

    items = _photos(total)
    groups = agrupar_fotos(items, seed=42)
    ordered_ids = [photo_id for group in groups for photo_id in group.photo_ids]

    assert sorted(ordered_ids) == sorted(photo.id for photo in items)
    assert len(ordered_ids) == len(set(ordered_ids)) == total
    assert {len(group.photo_ids) for group in groups} <= {1, 2, 4}


def test_agrupar_fotos_preserves_local_sequence_and_narrative_rhythm():
    from provas.narrativa import agrupar_fotos

    items = _photos(31)
    groups = agrupar_fotos(items, seed=9)
    ordered_ids = [photo_id for group in groups for photo_id in group.photo_ids]
    output_positions = {photo_id: position for position, photo_id in enumerate(ordered_ids)}

    assert groups[0].role == "opening" and len(groups[0].photo_ids) == 1
    assert groups[-1].role == "ending" and len(groups[-1].photo_ids) == 1
    assert all(abs(photo.index - output_positions[photo.id]) <= 8 for photo in items)
    longest_dense_run = current_dense_run = 0
    for group in groups:
        current_dense_run = current_dense_run + 1 if group.density == "dense" else 0
        longest_dense_run = max(longest_dense_run, current_dense_run)
    assert longest_dense_run <= 2


def test_agrupar_fotos_splits_a_three_photo_remainder_as_single_and_pair():
    from provas.narrativa import agrupar_fotos

    groups = agrupar_fotos(_photos(5), seed=1)

    assert [len(group.photo_ids) for group in groups[1:-1]] == [1, 2]


def test_photo_groups_are_immutable_and_seeded_results_are_repeatable():
    from provas.narrativa import agrupar_fotos

    first = agrupar_fotos(_photos(17), seed=123)
    second = agrupar_fotos(_photos(17), seed=123)

    assert first == second
    with pytest.raises(FrozenInstanceError):
        first[0].role = "changed"


def test_agrupar_fotos_uses_seed_for_repeatable_narrative_variation():
    from provas.narrativa import agrupar_fotos

    first = agrupar_fotos(_photos(17), seed=0)
    second = agrupar_fotos(_photos(17), seed=1)

    assert first != second


def test_agrupar_fotos_prefers_a_nearby_complement_over_a_similar_neighbor():
    from provas.narrativa import agrupar_fotos

    items = _photos(12)
    items[0] = PhotoInfo(**{**items[0].__dict__, "quality": 1.0})
    items[11] = PhotoInfo(**{**items[11].__dict__, "quality": 0.99})
    for index in range(1, 11):
        items[index] = PhotoInfo(**{**items[index].__dict__, "quality": 0.4, "similarity_group": index})
    items[2] = PhotoInfo(**{**items[2].__dict__, "similarity_group": 1})

    groups = agrupar_fotos(items, seed=1)
    first_sequence = groups[1].photo_ids

    assert "p1" in first_sequence
    assert "p3" in first_sequence
    assert "p2" not in first_sequence


def test_score_cover_is_deterministic_and_favours_quality_with_diversity():
    from provas.narrativa import score_cover

    items = _photos(8)
    ranked = score_cover(items)

    assert ranked == score_cover(items)
    assert ranked[0].id == "p0"
    assert len({photo.id for photo in ranked}) == len(items)


def test_agrupar_fotos_never_moves_adversarial_local_candidates_beyond_eight_positions():
    from provas.narrativa import agrupar_fotos

    values = random.Random(20260803)
    signals = list(zip(*[[values.random() for _ in range(15)] for _ in range(4)]))
    items = [
        PhotoInfo(
            id=f"p{index}", path=f"p{index}.jpg", label=f"P {index}", width=120, height=180,
            index=index, sharpness=signals[index][3], exposure=signals[index][0], density=signals[index][1],
            quality=signals[index][2], similarity_group=None,
        )
        for index in range(15)
    ]

    groups = agrupar_fotos(items, seed=157)
    ordered_ids = [photo_id for group in groups for photo_id in group.photo_ids]
    positions = {photo_id: output for output, photo_id in enumerate(ordered_ids)}

    assert positions["p4"] != 13  # Before the fix, p4 was emitted at output position 13.
    assert all(abs(photo.index - positions[photo.id]) <= 8 for photo in items)


def test_score_cover_promotes_distinct_similarity_group_after_a_leader():
    from provas.narrativa import score_cover

    leader = PhotoInfo("leader", "leader.jpg", "Leader", 120, 180, 0, quality=0.90, exposure=0.8, similarity_group=1)
    duplicate = PhotoInfo("duplicate", "duplicate.jpg", "Duplicate", 120, 180, 1, quality=0.89, exposure=0.8, similarity_group=1)
    distinct = PhotoInfo("distinct", "distinct.jpg", "Distinct", 120, 180, 2, quality=0.85, exposure=0.8, similarity_group=2)

    ranked = score_cover([leader, duplicate, distinct])

    assert [photo.id for photo in ranked[:2]] == ["leader", "distinct"]


def test_score_cover_rewards_higher_exposure_quality_not_midpoint_brightness():
    from provas.narrativa import score_cover

    midpoint = PhotoInfo("mid", "mid.jpg", "Mid", 120, 180, 0, quality=0.70, exposure=0.5, similarity_group=1)
    well_exposed = PhotoInfo("high", "high.jpg", "High", 120, 180, 1, quality=0.70, exposure=0.9, similarity_group=2)

    assert score_cover([midpoint, well_exposed])[0].id == "high"
