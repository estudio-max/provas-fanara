"""Persistence, reversible regeneration and diagnostics for editorial projects.

Project files deliberately contain only reproducible metadata.  Image data is
kept in the source folder and is never copied into the project JSON.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Iterable, Mapping

from .compositor import compose
from .modelos import BookPlan, PagePlan, PhotoInfo
from .motor import Config


PROJECT_SCHEMA_VERSION = 1
LONG_ALBUM_PAGE_LIMIT = 20
LOW_QUALITY_THRESHOLD = 0.35


class ProjectSchemaError(ValueError):
    """Raised when a project file cannot be safely read by this version."""


@dataclass(frozen=True)
class ProjectState:
    """All serializable state needed to reopen an editorial project.

    ``photo_paths`` and ``cache_keys`` are references only; neither carries
    image contents.  ``missing_paths`` is evaluated on demand so moving a
    source folder never makes loading the metadata fail.
    """

    config: Config
    plan: BookPlan
    photo_paths: tuple[str, ...] = ()
    cache_keys: tuple[str, ...] = ()
    previous_plan: BookPlan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "photo_paths", tuple(self.photo_paths))
        object.__setattr__(self, "cache_keys", tuple(self.cache_keys))

    @property
    def missing_paths(self) -> tuple[str, ...]:
        return tuple(path for path in self.photo_paths if not os.path.exists(path))


@dataclass(frozen=True)
class DiagnosticSummary:
    valid_count: int
    failed_count: int
    page_count: int
    distribution: Mapping[int, int]
    preserved_order_percent: float
    missing_paths: tuple[str, ...]
    warnings: tuple[str, ...]


def _plan_to_data(plan: BookPlan) -> dict[str, object]:
    return {
        "seed": plan.seed,
        "mode": plan.mode,
        "cover_photo_ids": list(plan.cover_photo_ids),
        "pages": [
            {
                "number": page.number,
                "template_id": page.template_id,
                "photo_ids": list(page.photo_ids),
                "role": page.role,
            }
            for page in plan.pages
        ],
    }


def _plan_from_data(data: object) -> BookPlan:
    if not isinstance(data, dict):
        raise ProjectSchemaError("Projeto inválido: plano ausente ou malformado.")
    try:
        pages_data = data["pages"]
        if not isinstance(pages_data, list):
            raise TypeError("pages")
        pages = tuple(
            PagePlan(
                int(page["number"]), str(page["template_id"]),
                tuple(str(photo_id) for photo_id in page["photo_ids"]), str(page["role"]),
            )
            for page in pages_data
        )
        return BookPlan(
            int(data["seed"]), str(data["mode"]),
            tuple(str(photo_id) for photo_id in data["cover_photo_ids"]), pages,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectSchemaError("Projeto inválido: plano malformado.") from exc


def _state_to_data(state: ProjectState) -> dict[str, object]:
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "config": asdict(state.config),
        "photo_paths": list(state.photo_paths),
        "cache_keys": list(state.cache_keys),
        "plan": _plan_to_data(state.plan),
        "previous_plan": _plan_to_data(state.previous_plan) if state.previous_plan else None,
    }


def _state_from_data(data: object) -> ProjectState:
    if not isinstance(data, dict):
        raise ProjectSchemaError("Projeto inválido: conteúdo JSON esperado.")
    version = data.get("schema_version")
    if version != PROJECT_SCHEMA_VERSION:
        raise ProjectSchemaError(f"A versão do projeto {version!r} não é suportada.")
    try:
        config_data = data["config"]
        if not isinstance(config_data, dict):
            raise TypeError("config")
        photo_paths = tuple(str(path) for path in data.get("photo_paths", ()))
        cache_keys = tuple(str(key) for key in data.get("cache_keys", ()))
        previous_data = data.get("previous_plan")
        return ProjectState(
            Config(**config_data), _plan_from_data(data["plan"]), photo_paths, cache_keys,
            _plan_from_data(previous_data) if previous_data is not None else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ProjectSchemaError):
            raise
        raise ProjectSchemaError("Projeto inválido: metadados malformados.") from exc


def _new_sibling_temp(destination: str) -> tuple[int, str]:
    absolute = os.path.abspath(destination)
    directory = os.path.dirname(absolute)
    os.makedirs(directory, exist_ok=True)
    return tempfile.mkstemp(
        dir=directory,
        prefix=f".{os.path.basename(absolute)}.",
        suffix=".tmp",
    )


def save_project(path: str | os.PathLike[str], state: ProjectState) -> None:
    """Atomically save state as UTF-8 JSON beside any existing project file."""
    destination = os.fspath(path)
    descriptor, temporary = _new_sibling_temp(destination)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(_state_to_data(state), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_project(path: str | os.PathLike[str]) -> ProjectState:
    """Load project metadata without opening, decoding or copying any image."""
    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ProjectSchemaError("Projeto inválido: JSON não pôde ser lido.") from exc
    return _state_from_data(data)


def _next_seed(seed: int) -> int:
    """A deterministic alternate seed that is always different from ``seed``."""
    return seed + 1


def regenerate(state: ProjectState, photos: Iterable[PhotoInfo]) -> ProjectState:
    """Compose a deterministic alternate plan and preserve manual cover picks."""
    items = tuple(photos)
    seed = _next_seed(state.plan.seed)
    config = replace(state.config, semente=seed)
    plan = compose(items, config.modo, seed, config.cover_ids)
    return ProjectState(config, plan, state.photo_paths, state.cache_keys, state.plan)


def undo_regeneration(state: ProjectState) -> ProjectState:
    """Restore the plan and seed immediately preceding the latest regeneration."""
    if state.previous_plan is None:
        raise ValueError("Não há uma regeneração para desfazer.")
    config = replace(state.config, semente=state.previous_plan.seed)
    return ProjectState(config, state.previous_plan, state.photo_paths, state.cache_keys)


def _longest_increasing_subsequence_length(values: Iterable[int]) -> int:
    """Return the number of photo positions retaining their source order."""
    tails: list[int] = []
    from bisect import bisect_left

    for value in values:
        index = bisect_left(tails, value)
        if index == len(tails):
            tails.append(value)
        else:
            tails[index] = value
    return len(tails)


def diagnostic_summary(
    state: ProjectState,
    photos: Iterable[PhotoInfo],
    failures: Iterable[tuple[str, str]] = (),
) -> DiagnosticSummary:
    """Summarize recoverable input issues without omitting any supplied photo."""
    items = tuple(photos)
    distribution = {count: 0 for count in (1, 2, 4)}
    for page in state.plan.pages:
        count = len(page.photo_ids)
        if count in distribution:
            distribution[count] += 1

    source_positions = {photo.id: position for position, photo in enumerate(items)}
    planned = [
        source_positions[photo_id]
        for page in state.plan.pages
        for photo_id in page.photo_ids
        if photo_id in source_positions
    ]
    denominator = max(1, min(len(items), len(planned)))
    preserved = round(_longest_increasing_subsequence_length(planned) * 100 / denominator, 1)
    missing = state.missing_paths
    failed_paths = {str(path) for path, _reason in failures}
    failed_count = len(failed_paths | set(missing))

    warnings: list[str] = []
    low_quality = [photo for photo in items if photo.quality < LOW_QUALITY_THRESHOLD]
    if low_quality:
        warnings.append(f"{len(low_quality)} foto(s) com baixa qualidade; elas continuam no álbum.")
    if missing:
        warnings.append(f"{len(missing)} foto(s) de origem ausente(s); o projeto foi mantido intacto.")
    if len(state.plan.pages) > LONG_ALBUM_PAGE_LIMIT:
        warnings.append("Álbum muito longo; considere dividir a seleção em volumes menores.")

    return DiagnosticSummary(
        valid_count=len(items), failed_count=failed_count, page_count=len(state.plan.pages),
        distribution=MappingProxyType(distribution), preserved_order_percent=preserved,
        missing_paths=missing, warnings=tuple(warnings),
    )
