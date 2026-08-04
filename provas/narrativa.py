"""Deterministic local grouping for a readable photobook sequence."""
from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Iterable

from .modelos import PhotoInfo


@dataclass(frozen=True)
class PhotoGroup:
    photo_ids: tuple[str, ...]
    role: str
    density: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "photo_ids", tuple(self.photo_ids))
        if len(self.photo_ids) not in {1, 2, 4}:
            raise ValueError("Photo groups must contain one, two, or four photographs")
        if self.density not in {"airy", "balanced", "dense"}:
            raise ValueError("Unknown group density")


def _cover_value(photo: PhotoInfo, seen_groups: set[int]) -> float:
    diversity = 0.18 if photo.similarity_group not in seen_groups else 0.0
    return photo.quality * 0.62 + photo.sharpness * 0.16 + photo.density * 0.10 + photo.exposure * 0.12 + diversity


def score_cover(items: Iterable[PhotoInfo]) -> list[PhotoInfo]:
    """Rank strong, visually varied candidates without random state."""
    remaining = sorted(items, key=lambda photo: (photo.index, photo.id))
    ranked: list[PhotoInfo] = []
    seen_groups: set[int] = set()
    while remaining:
        best = max(remaining, key=lambda photo: (_cover_value(photo, seen_groups), -photo.index, photo.id))
        ranked.append(best)
        if best.similarity_group is not None:
            seen_groups.add(best.similarity_group)
        remaining.remove(best)
    return ranked


def _middle_sizes(count: int, rng: random.Random) -> list[int]:
    """Use only 1/2/4 slots and put a pause after at most two dense groups."""
    sizes: list[int] = []
    dense_run = 0
    remaining = count
    while remaining:
        if remaining == 3:
            sizes.extend((1, 2))
            break
        choices = [size for size in (4, 2, 1) if remaining >= size and remaining - size != 3]
        if dense_run >= 2:
            choices = [size for size in choices if size != 4] or choices
        # A four-photo spread is efficient, while a seeded weighted choice changes
        # the rhythm reproducibly without violating the remainder constraint.
        weights = {4: 5, 2: 3, 1: 1}
        size = rng.choices(choices, weights=[weights[option] for option in choices], k=1)[0]
        sizes.append(size)
        remaining -= size
        dense_run = dense_run + 1 if size == 4 else 0
    return sizes


def _best_in_window(
    items: list[PhotoInfo], window: range, exclude: set[str], ranks: dict[str, int]
) -> PhotoInfo:
    candidates = [items[index] for index in window if items[index].id not in exclude]
    return max(
        candidates,
        key=lambda photo: (photo.quality, photo.sharpness, photo.density, -ranks[photo.id], photo.id),
    )


def _different_group(candidate: PhotoInfo, selected: list[PhotoInfo]) -> float:
    if candidate.similarity_group is None:
        return 1.0
    return float(all(candidate.similarity_group != photo.similarity_group for photo in selected))


def _take_adjacent_complements(
    remaining: list[PhotoInfo], size: int, output_start: int, ranks: dict[str, int]
) -> list[PhotoInfo]:
    """Diversify a local group without moving a valid-photo rank more than eight slots."""
    selected: list[PhotoInfo] = []
    while len(selected) < size:
        output_position = output_start + len(selected)
        candidates = [
            photo for photo in remaining
            if abs(ranks[photo.id] - output_position) <= 8
        ]
        if not candidates:
            raise ValueError("Cannot satisfy the eight-position narrative movement limit")

        due = [photo for photo in candidates if ranks[photo.id] <= output_position - 8]
        if due:
            candidates = due
        elif not selected and remaining[0] in candidates:
            candidates = [remaining[0]]

        def value(candidate: PhotoInfo) -> tuple[float, float, int, str]:
            distance = abs(ranks[candidate.id] - output_position)
            contrast = max(
                abs(candidate.density - photo.density) + abs(candidate.exposure - photo.exposure)
                for photo in selected
            ) if selected else 0.0
            return (_different_group(candidate, selected), contrast, -distance, candidate.id)

        choice = max(candidates, key=value)
        remaining.remove(choice)
        selected.append(choice)
    return selected


def agrupar_fotos(items: Iterable[PhotoInfo], seed: int) -> tuple[PhotoGroup, ...]:
    """Make local, template-compatible narrative beats from each valid photo once."""
    ordered = sorted(items, key=lambda photo: (photo.index, photo.id))
    if not ordered:
        return ()
    if len(ordered) == 1:
        return (PhotoGroup((ordered[0].id,), "opening", "airy"),)

    rng = random.Random(seed)
    ranks = {photo.id: rank for rank, photo in enumerate(ordered)}
    opening = _best_in_window(ordered, range(min(9, len(ordered))), set(), ranks)
    ending = _best_in_window(
        ordered, range(max(0, len(ordered) - 9), len(ordered)), {opening.id}, ranks
    )
    remaining = [photo for photo in ordered if photo.id not in {opening.id, ending.id}]

    groups = [PhotoGroup((opening.id,), "opening", "airy")]
    output_position = 1
    for size in _middle_sizes(len(remaining), rng):
        selection = _take_adjacent_complements(remaining, size, output_position, ranks)
        output_position += size
        density = "dense" if size == 4 else "balanced" if size == 2 else "airy"
        role = "sequence" if size > 1 else "pause"
        groups.append(PhotoGroup(tuple(photo.id for photo in selection), role, density))
    groups.append(PhotoGroup((ending.id,), "ending", "airy"))
    return tuple(groups)
