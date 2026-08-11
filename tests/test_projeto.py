from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from provas.compositor import compose, validate_plan
from provas.modelos import PhotoInfo
from provas.motor import Config


def _photos(root: Path, total: int = 9) -> tuple[PhotoInfo, ...]:
    return tuple(
        PhotoInfo(
            id=str(root / f"foto-{number}.jpg"),
            path=str(root / f"foto-{number}.jpg"),
            label=f"Foto {number}", width=300, height=450, index=number,
            sharpness=0.7, exposure=0.7, density=0.6,
            quality=0.8 if number else 0.15, similarity_group=number,
        )
        for number in range(total)
    )


def _state(root: Path, total: int = 9):
    from provas.projeto import ProjectState

    photos = _photos(root, total)
    for photo in photos:
        Path(photo.path).write_bytes(b"source is not persisted")
    config = Config(
        pasta=str(root), saida=str(root / "álbum final.pdf"), titulo="Coração & Luz",
        modo="fotolivro", semente=41, cover_ids=tuple(photo.id for photo in photos[:2]),
    )
    plan = compose(photos, config.modo, config.semente, config.cover_ids)
    return ProjectState(config, plan, tuple(photo.path for photo in photos), ("análise-v1",)), photos


def test_save_and_load_round_trip_unicode_windows_metadata_without_image_bytes(tmp_path: Path):
    from provas.projeto import PROJECT_SCHEMA_VERSION, load_project, save_project

    folder = tmp_path / "Casamento da Júlia & João"
    folder.mkdir()
    state, _ = _state(folder)
    destination = folder / "projeto fotolivro.json"

    save_project(destination, state)
    raw = destination.read_text(encoding="utf-8")
    payload = json.loads(raw)

    assert payload["schema_version"] == PROJECT_SCHEMA_VERSION == 3
    assert "Júlia" in raw
    assert "\\u00fa" not in raw
    assert "image_bytes" not in raw
    assert load_project(destination) == state


def test_save_and_reopen_preserves_an_exact_per_page_layout_choice(tmp_path: Path):
    from provas.ciclo_paginas import ciclar_pagina
    from provas.projeto import load_project, save_project

    state, photos = _state(tmp_path, total=17)
    ratios = {photo.id: photo.width / photo.height for photo in photos}
    page_number = next(
        page.number for page in state.plan.pages
        if ciclar_pagina(state.plan, page.number, ratios) != state.plan
    )
    cycled = replace(state.plan, pages=ciclar_pagina(state.plan, page_number, ratios).pages)
    destination = tmp_path / "ciclado.provas.json"

    save_project(destination, replace(state, plan=cycled))

    assert load_project(destination).plan == cycled


def test_load_migrates_v1_project_to_default_cover_style_without_losing_identity(tmp_path: Path):
    from provas import projeto

    state, _ = _state(tmp_path)
    legacy = projeto._state_to_data(state)
    legacy["schema_version"] = 1
    legacy["config"].pop("estilo_capa")
    legacy["config"].update({
        "estudio": "Estúdio Fanara",
        "site": "fanara.example",
        "logo": "C:\\identidade\\marca.png",
    })
    source = tmp_path / "legado.json"
    source.write_text(json.dumps(legacy), encoding="utf-8")

    migrated = projeto.load_project(source)
    destination = tmp_path / "migrado.json"
    projeto.save_project(destination, migrated)

    assert migrated.config.estilo_capa == "mosaico"
    assert migrated.config.estudio == "Estúdio Fanara"
    assert migrated.config.site == "fanara.example"
    assert migrated.config.logo == "C:\\identidade\\marca.png"
    assert json.loads(destination.read_text(encoding="utf-8"))["schema_version"] == 3


def test_new_projects_default_to_classic_cover(tmp_path: Path):
    from provas.projeto import ProjectConfig

    config = ProjectConfig(pasta=str(tmp_path))

    assert config.estilo_capa == "classica"
    assert config.foto_capa_id == ""
    assert (config.capa_foco_x, config.capa_foco_y, config.capa_zoom) == (0.5, 0.5, 1.0)
    assert config.capa_enquadramento == "automatico"


def test_v2_project_keeps_mosaic_when_classic_fields_are_absent(tmp_path: Path):
    from provas import projeto

    state, _ = _state(tmp_path)
    payload = projeto._state_to_data(state)
    payload["schema_version"] = 2
    payload["config"]["estilo_capa"] = "mosaico"
    for field in (
        "foto_capa_id", "capa_foco_x", "capa_foco_y", "capa_zoom", "capa_enquadramento",
    ):
        payload["config"].pop(field, None)
    source = tmp_path / "v2.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    migrated = projeto.load_project(source)

    assert migrated.config.estilo_capa == "mosaico"
    assert migrated.config.foto_capa_id == ""
    assert migrated.config.cover_ids == state.config.cover_ids
    assert migrated.plan == state.plan
    assert migrated.previous_plan == state.previous_plan


def test_v2_project_without_cover_style_migrates_to_mosaic(tmp_path: Path):
    from provas import projeto

    state, _ = _state(tmp_path)
    payload = projeto._state_to_data(state)
    payload["schema_version"] = 2
    payload["config"].pop("estilo_capa")
    source = tmp_path / "v2-sem-estilo.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    migrated = projeto.load_project(source)

    assert migrated.config.estilo_capa == "mosaico"


def test_crop_values_are_normalized():
    from provas.projeto import ProjectConfig

    config = ProjectConfig(pasta="x", capa_foco_x=-2, capa_foco_y=4, capa_zoom=8)

    assert (config.capa_foco_x, config.capa_foco_y, config.capa_zoom) == (0.0, 1.0, 2.5)


def test_project_config_rejects_invalid_cover_framing():
    from provas.projeto import ProjectConfig

    with pytest.raises(ValueError, match="Enquadramento da capa inválido."):
        ProjectConfig(pasta="x", capa_enquadramento="livre")


def test_project_config_rejects_unknown_cover_style_in_portuguese(tmp_path: Path):
    from provas.projeto import ProjectConfig

    with pytest.raises(
        ValueError,
        match="Estilo de capa inválido. Use classica, mosaico ou curvas_editoriais.",
    ):
        ProjectConfig(pasta=str(tmp_path), estilo_capa="desconhecido")


def test_project_state_snapshots_config_so_external_or_direct_mutation_cannot_diverge_seed(tmp_path: Path):
    from provas.projeto import ProjectState

    photos = _photos(tmp_path)
    mutable = Config(str(tmp_path), modo="fotolivro", semente=41, cover_ids=(photos[0].id,))
    state = ProjectState(mutable, compose(photos, "fotolivro", 41, mutable.cover_ids))
    mutable.semente = 999

    assert state.config.semente == state.plan.seed == 41
    with pytest.raises((AttributeError, TypeError)):
        state.config.semente = 999


def test_load_reports_missing_source_paths_exactly_without_failing(tmp_path: Path):
    from provas.projeto import load_project, save_project

    state, _ = _state(tmp_path, total=2)
    missing = Path(state.photo_paths[1])
    missing.unlink()
    destination = tmp_path / "project.json"
    save_project(destination, state)

    loaded = load_project(destination)

    assert loaded.missing_paths == (str(missing),)


def test_load_rejects_a_future_schema_in_portuguese(tmp_path: Path):
    from provas.projeto import ProjectSchemaError, load_project

    destination = tmp_path / "future.json"
    destination.write_text(json.dumps({"schema_version": 4}), encoding="utf-8")

    with pytest.raises(ProjectSchemaError, match="versão.*não é suportada"):
        load_project(destination)


def test_load_rejects_page_photo_that_is_not_part_of_the_project(tmp_path: Path):
    from provas import projeto

    state, _ = _state(tmp_path)
    payload = projeto._state_to_data(state)
    payload["plan"]["pages"][0]["photo_ids"] = [str(tmp_path / "intrusa.jpg")]
    source = tmp_path / "foto-intrusa.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(projeto.ProjectSchemaError, match="não pertence ao projeto"):
        projeto.load_project(source)


def test_load_rejects_all_page_photos_when_none_belong_to_the_project(tmp_path: Path):
    from provas import projeto

    state, _ = _state(tmp_path)
    payload = projeto._state_to_data(state)
    payload["photo_paths"] = [str(tmp_path / "outra-foto.jpg")]
    source = tmp_path / "todas-fotos-intrusas.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(projeto.ProjectSchemaError, match="não pertence ao projeto"):
        projeto.load_project(source)


def test_load_rejects_page_template_with_incompatible_photo_count(tmp_path: Path):
    from provas import projeto

    state, _ = _state(tmp_path)
    payload = projeto._state_to_data(state)
    payload["plan"]["pages"][0]["template_id"] = "pair-asymmetric-left"
    source = tmp_path / "aridade-invalida.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(projeto.ProjectSchemaError, match="quantidade de fotos incompatível"):
        projeto.load_project(source)


def test_load_rejects_unknown_templates_when_no_page_uses_the_catalog(tmp_path: Path):
    from provas import projeto

    state, _ = _state(tmp_path)
    payload = projeto._state_to_data(state)
    for page in payload["plan"]["pages"]:
        page["template_id"] = "template-desconhecido"
    source = tmp_path / "templates-inexistentes.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(projeto.ProjectSchemaError, match="template.*não existe"):
        projeto.load_project(source)


def test_save_is_atomic_and_cleans_its_unique_sibling_temp_on_replace_failure(tmp_path: Path, monkeypatch):
    from provas import projeto

    state, _ = _state(tmp_path)
    destination = tmp_path / "original.json"
    destination.write_text("conteúdo anterior", encoding="utf-8")

    def fail_replace(source: str, target: str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(projeto.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        projeto.save_project(destination, state)

    assert destination.read_text(encoding="utf-8") == "conteúdo anterior"
    assert not list(tmp_path.glob(".original.json.*.tmp"))


def test_regeneration_changes_seed_keeps_manual_covers_and_undo_restores_plan(tmp_path: Path):
    from provas.projeto import regenerate, undo_regeneration

    state, photos = _state(tmp_path, total=17)

    regenerated = regenerate(state, photos)

    assert regenerated.plan.seed != state.plan.seed
    assert regenerated.config.semente == regenerated.plan.seed
    assert regenerated.plan.cover_photo_ids[:2] == state.config.cover_ids
    assert regenerated.previous_plan == state.plan
    assert validate_plan(regenerated.plan, photos) == ()
    assert undo_regeneration(regenerated).plan == state.plan
    assert undo_regeneration(regenerated).config.semente == state.config.semente


def test_regeneration_is_deterministic_for_the_same_project_state(tmp_path: Path):
    from provas.projeto import regenerate

    state, photos = _state(tmp_path, total=17)

    assert regenerate(state, photos) == regenerate(state, photos)


def test_diagnostic_summary_counts_pages_distribution_order_and_warnings(tmp_path: Path):
    from provas.projeto import diagnostic_summary

    state, photos = _state(tmp_path, total=9)
    missing = tmp_path / "ausente.jpg"
    state = replace(state, photo_paths=(*state.photo_paths, str(missing)))
    bad = tmp_path / "corrompida.jpg"
    reordered = tuple(reversed(photos))

    summary = diagnostic_summary(state, reordered, failures=((str(bad), "arquivo inválido"),))

    assert summary.valid_count == len(photos)
    assert summary.failed_count == 2
    assert summary.page_count == len(state.plan.pages)
    assert set(summary.distribution) == {1, 2, 4}
    assert sum(summary.distribution.values()) == summary.page_count
    assert summary.preserved_order_percent < 100
    assert summary.missing_paths == (str(missing),)
    assert any("qualidade" in warning.lower() for warning in summary.warnings)


def test_diagnostic_warns_about_an_overly_long_album_without_excluding_photos(tmp_path: Path):
    from provas.projeto import diagnostic_summary

    state, photos = _state(tmp_path, total=81)
    summary = diagnostic_summary(state, photos)

    assert summary.valid_count == len(photos)
    assert any("longo" in warning.lower() for warning in summary.warnings)
