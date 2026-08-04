"""Immutable value objects shared by the editorial photobook pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhotoInfo:
    id: str
    path: str
    label: str
    width: int
    height: int
    index: int
    sharpness: float = 0.0
    exposure: float = 0.5
    density: float = 0.5
    quality: float = 0.5
    similarity_group: int | None = None


@dataclass(frozen=True)
class Rect:
    """A rectangle in normalized page coordinates, unless a caller states otherwise."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise ValueError("Rectangle dimensions cannot be negative")

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class Slot:
    """One image allocation and its optional caption allocation."""

    rect: Rect
    caption: Rect = Rect(0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Template:
    """A reusable normalized page layout for one, two, or four photographs."""

    id: str
    slots: tuple[Slot, ...]
    orientations: frozenset[str]
    hierarchy_weight: float
    density_class: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", tuple(self.slots))
        object.__setattr__(self, "orientations", frozenset(self.orientations))
        if len(self.slots) not in {1, 2, 4}:
            raise ValueError("Templates must contain one, two, or four slots")
        if not self.orientations:
            raise ValueError("Templates must accept at least one orientation")
        if self.density_class not in {"airy", "balanced", "dense"}:
            raise ValueError("Unknown density class")
        for slot in self.slots:
            if not (0 <= slot.rect.x <= 1 and 0 <= slot.rect.y <= 1):
                raise ValueError("Slot positions must be normalized")
            if slot.rect.right > 1 or slot.rect.bottom > 1:
                raise ValueError("Slots must stay within the normalized page")

    def resolve(self, mode: str) -> Template:
        """Return the mode-specific layout without mutating the catalog template."""
        if mode not in {"prova", "fotolivro"}:
            raise ValueError(f"Unsupported mode: {mode}")
        if mode == "fotolivro":
            blank = Rect(0.0, 0.0, 0.0, 0.0)
            return Template(
                self.id,
                tuple(Slot(slot.rect, blank) for slot in self.slots),
                self.orientations,
                self.hierarchy_weight,
                self.density_class,
            )

        resolved_slots = []
        for slot in self.slots:
            caption_height = min(0.045, slot.rect.height * 0.22)
            image = Rect(slot.rect.x, slot.rect.y, slot.rect.width, slot.rect.height - caption_height)
            caption = Rect(slot.rect.x, image.bottom, slot.rect.width, caption_height)
            resolved_slots.append(Slot(image, caption))
        return Template(
            self.id,
            tuple(resolved_slots),
            self.orientations,
            self.hierarchy_weight,
            self.density_class,
        )


@dataclass(frozen=True)
class PagePlan:
    number: int
    template_id: str
    photo_ids: tuple[str, ...]
    role: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "photo_ids", tuple(self.photo_ids))


@dataclass(frozen=True)
class BookPlan:
    seed: int
    mode: str
    cover_photo_ids: tuple[str, ...]
    pages: tuple[PagePlan, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cover_photo_ids", tuple(self.cover_photo_ids))
        object.__setattr__(self, "pages", tuple(self.pages))
