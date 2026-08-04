"""Declarative editorial layouts and no-crop image geometry."""

from __future__ import annotations

from typing import Any

from .modelos import Rect, Slot, Template


_MARGIN = 0.055
_GAP = 0.025


def _rect(x: float, y: float, width: float, height: float) -> Slot:
    return Slot(Rect(x, y, width, height))


_CATALOG: tuple[Template, ...] = (
    Template("single-portrait", (_rect(0.33, _MARGIN, 0.34, 0.89),), frozenset({"portrait"}), 1.0, "airy"),
    Template("single-landscape", (_rect(_MARGIN, 0.20, 0.89, 0.60),), frozenset({"landscape"}), 1.0, "airy"),
    Template("single-full", (_rect(_MARGIN, _MARGIN, 0.89, 0.89),), frozenset({"portrait", "landscape", "square"}), 0.9, "balanced"),
    Template("single-square-framed", (_rect(0.22, 0.22, 0.56, 0.56),), frozenset({"square"}), 0.85, "airy"),
    Template("pair-portraits", (_rect(0.12, _MARGIN, 0.34, 0.89), _rect(0.54, _MARGIN, 0.34, 0.89)), frozenset({"portrait"}), 0.8, "balanced"),
    Template("pair-landscapes", (_rect(_MARGIN, 0.14, 0.89, 0.32), _rect(_MARGIN, 0.54, 0.89, 0.32)), frozenset({"landscape"}), 0.8, "balanced"),
    Template("pair-squares", (_rect(0.10, 0.29, 0.38, 0.38), _rect(0.52, 0.29, 0.38, 0.38)), frozenset({"square"}), 0.85, "balanced"),
    Template("pair-asymmetric-left", (_rect(_MARGIN, _MARGIN, 0.53, 0.89), _rect(0.61, _MARGIN, 0.33, 0.89)), frozenset({"portrait", "landscape", "mixed"}), 1.1, "balanced"),
    Template("pair-asymmetric-right", (_rect(_MARGIN, _MARGIN, 0.33, 0.89), _rect(0.42, _MARGIN, 0.53, 0.89)), frozenset({"portrait", "landscape", "mixed"}), 1.1, "balanced"),
    Template("pair-breathing", (_rect(0.12, 0.18, 0.33, 0.64), _rect(0.55, 0.18, 0.33, 0.64)), frozenset({"portrait", "landscape", "mixed"}), 0.7, "airy"),
    Template("quad-grid", (_rect(_MARGIN, _MARGIN, 0.42, 0.42), _rect(0.525, _MARGIN, 0.42, 0.42), _rect(_MARGIN, 0.525, 0.42, 0.42), _rect(0.525, 0.525, 0.42, 0.42)), frozenset({"portrait", "landscape", "mixed", "square"}), 0.6, "dense"),
    Template("quad-left-feature", (_rect(_MARGIN, _MARGIN, 0.42, 0.89), _rect(0.525, _MARGIN, 0.42, 0.27), _rect(0.525, 0.365, 0.42, 0.27), _rect(0.525, 0.675, 0.42, 0.27)), frozenset({"portrait", "landscape", "mixed"}), 0.9, "dense"),
    Template("quad-top-feature", (_rect(_MARGIN, _MARGIN, 0.89, 0.32), _rect(_MARGIN, 0.415, 0.27, 0.49), _rect(0.365, 0.415, 0.27, 0.49), _rect(0.675, 0.415, 0.27, 0.49)), frozenset({"portrait", "landscape", "mixed"}), 0.9, "dense"),
    Template("quad-columns", (_rect(_MARGIN, _MARGIN, 0.20, 0.89), _rect(0.29, _MARGIN, 0.20, 0.89), _rect(0.51, _MARGIN, 0.20, 0.89), _rect(0.73, _MARGIN, 0.20, 0.89)), frozenset({"portrait", "mixed"}), 0.7, "dense"),
)


def catalog() -> tuple[Template, ...]:
    """Return the curated immutable template catalog."""
    return _CATALOG


def fit_contain(bounds: Rect, ratio: float) -> Rect:
    """Center a rectangle with ``ratio`` inside bounds, never cropping or stretching."""
    if ratio <= 0:
        raise ValueError("ratio must be greater than zero")
    if bounds.width == 0 or bounds.height == 0:
        return Rect(bounds.x, bounds.y, 0.0, 0.0)
    bound_ratio = bounds.width / bounds.height
    if ratio >= bound_ratio:
        width = bounds.width
        height = width / ratio
    else:
        height = bounds.height
        width = height * ratio
    return Rect(bounds.x + (bounds.width - width) / 2, bounds.y + (bounds.height - height) / 2, width, height)


def _group_orientation(group: Any) -> str | None:
    if isinstance(group, str):
        return group
    orientation = getattr(group, "orientation", None)
    if isinstance(orientation, str):
        return orientation
    orientations = getattr(group, "orientations", None)
    if isinstance(orientations, str):
        return orientations
    if orientations:
        unique_orientations = frozenset(orientations)
        if len(unique_orientations) == 1:
            return next(iter(unique_orientations))
        return "mixed"
    return None


def compatible_templates(group: Any, previous_id: str | None = None) -> tuple[Template, ...]:
    """Select layouts that accept a group's orientation and avoid immediate repeats."""
    orientation = _group_orientation(group)
    return tuple(
        template
        for template in _CATALOG
        if template.id != previous_id and (orientation is None or orientation in template.orientations)
    )
