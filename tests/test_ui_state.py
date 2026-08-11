from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QLineEdit
from PySide6.QtTest import QTest

from provas.modelos import BookPlan, PagePlan
from provas.motor import Config, Resultado


def _relative_luminance(color: str) -> float:
    """WCAG 2.2 relative luminance for an exact six-digit sRGB token."""
    values = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in values
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _qss_property(qss: str, selector: str, property_name: str) -> str:
    start = qss.index(selector)
    block = qss[qss.index("{", start) + 1:qss.index("}", start)]
    match = re.search(rf"{re.escape(property_name)}:\s*(#[0-9A-Fa-f]{{6}})", block)
    assert match is not None, f"{property_name} ausente em {selector}"
    return match.group(1)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def plan(tmp_path: Path) -> BookPlan:
    photos = tuple(str(tmp_path / f"D61_{number:04d}.jpg") for number in range(1, 5))
    return BookPlan(
        seed=7,
        mode="prova",
        cover_photo_ids=photos[:2],
        pages=(
            PagePlan(1, "single-landscape", (photos[0],), "opening"),
            PagePlan(2, "pair-asymmetric-left", photos[1:3], "ending"),
        ),
    )


def test_initial_actions_are_disabled_until_a_folder_is_selected(qapp, tmp_path: Path):
    from provas.ui import MainWindow

    window = MainWindow()

    assert not window.sidebar.analyze_button.isEnabled()
    assert not window.export_button.isEnabled()
    assert not window.sidebar.cover_button.isEnabled()
    assert not window.preview_grid.regenerate_button.isEnabled()

    window.select_folder(str(tmp_path))

    assert window.sidebar.analyze_button.isEnabled()
    assert window.folder_path == str(tmp_path)
    assert "pasta" in window.status_message.lower()


def test_open_project_restores_exact_editorial_state_without_analysis(
    qapp, tmp_path: Path, plan, monkeypatch
):
    from provas.projeto import ProjectState, save_project
    from provas.ui import MainWindow

    previous = replace(plan, seed=plan.seed - 1)
    manual_cover = tuple(reversed(plan.cover_photo_ids))
    for photo_id in {photo_id for page in plan.pages for photo_id in page.photo_ids}:
        Image.new("RGB", (300, 450), (80, 90, 100)).save(photo_id)
    state = ProjectState(
        Config(
            str(tmp_path),
            saida=str(tmp_path / "entrega.pdf"),
            titulo="Ensaio Aurora",
            estudio="Estúdio Fanara",
            site="fanara.com.br",
            logo=str(tmp_path / "marca.png"),
            estilo_capa="curvas_editoriais",
            modo="fotolivro",
            marca_dagua=False,
            mostrar_codigos=False,
            semente=plan.seed,
            cover_ids=manual_cover,
        ),
        replace(plan, mode="fotolivro", cover_photo_ids=manual_cover),
        tuple(photo_id for page in plan.pages for photo_id in page.photo_ids),
        ("cache-a", "cache-b"),
        replace(previous, mode="fotolivro"),
    )
    project = tmp_path / "aurora.provas.json"
    save_project(project, state)
    window = MainWindow()
    preview_requests: list[bool] = []
    monkeypatch.setattr(window, "request_preview", lambda: preview_requests.append(True))

    window.open_project(str(project))

    assert window.project_state == state
    assert window._draft_config == state.config.to_motor_config()
    assert window.folder_path == str(tmp_path)
    assert window.mode == "fotolivro"
    assert window.sidebar.cover_style.currentData() == "curvas_editoriais"
    assert window.sidebar.title_edit.text() == "Ensaio Aurora"
    assert window.sidebar.studio_edit.text() == "Estúdio Fanara"
    assert window.sidebar.site_edit.text() == "fanara.com.br"
    assert window.sidebar.logo_path == str(tmp_path / "marca.png")
    assert window.diagnostics.pages_value.text() == str(len(plan.pages))
    assert preview_requests == [True]
    assert window.status_kind == "success"
    assert "aberto" in window.status_message.lower()


def test_open_project_dialog_is_accessible_and_uses_project_file_filter(
    qapp, tmp_path: Path, monkeypatch
):
    from provas.projeto import ProjectState, save_project
    from provas.ui import MainWindow

    photo = str(tmp_path / "foto.jpg")
    plan = BookPlan(3, "prova", (photo,), (PagePlan(1, "single-portrait", (photo,), "opening"),))
    project = tmp_path / "sessao.provas.json"
    save_project(project, ProjectState(Config(str(tmp_path)), plan, (photo,)))
    window = MainWindow()
    captured: list[tuple[str, str]] = []

    def choose(_parent, title, _default, file_filter):
        captured.append((title, file_filter))
        return str(project), file_filter

    monkeypatch.setattr(QFileDialog, "getOpenFileName", choose)
    monkeypatch.setattr(window, "request_preview", lambda: None)

    window.open_project_button.click()

    assert captured == [("Abrir projeto", "Projeto Fotolivro (*.provas.json);;JSON (*.json)")]
    assert window.open_project_button.accessibleName() == "Abrir projeto Fotolivro"
    assert "Ctrl+O" in {shortcut.key().toString() for shortcut in window.findChildren(QShortcut)}
    assert window.project_state is not None


def test_sidebar_exposes_three_cover_styles_and_accessible_identity_fields(qapp):
    from provas.ui.sidebar import WorkflowSidebar

    sidebar = WorkflowSidebar()

    assert [sidebar.cover_style.itemData(index) for index in range(sidebar.cover_style.count())] == [
        "classica",
        "mosaico",
        "curvas_editoriais",
    ]
    assert [sidebar.cover_style.itemText(index) for index in range(sidebar.cover_style.count())] == [
        "Clássica",
        "Mosaico editorial",
        "Curvas editoriais",
    ]
    assert sidebar.title_edit.accessibleName() == "Título da capa"
    assert sidebar.studio_edit.accessibleName() == "Nome do fotógrafo ou estúdio"
    assert sidebar.site_edit.accessibleName() == "Site do fotógrafo ou estúdio"
    assert sidebar.logo_choose_button.accessibleName() == "Escolher logotipo da capa"
    assert sidebar.logo_remove_button.accessibleName() == "Remover logotipo da capa"
    assert sidebar.crop_button.accessibleName() == "Ajustar enquadramento"
    assert all(edit.minimumHeight() >= 36 for edit in sidebar.findChildren(QLineEdit))


def test_classic_crop_action_requires_ready_classic_project(qapp):
    from provas.ui.sidebar import WorkflowSidebar

    sidebar = WorkflowSidebar()
    assert not sidebar.crop_button.isEnabled()

    sidebar.set_cover_ready(True)
    assert not sidebar.crop_button.isEnabled()
    sidebar.set_crop_ready(True)
    assert sidebar.crop_button.isEnabled()

    sidebar.set_cover_style("mosaico")
    assert not sidebar.crop_button.isEnabled()

    sidebar.set_cover_style("classica")
    assert sidebar.crop_button.isEnabled()

    sidebar.set_busy(True, "Preparando prévia")
    assert not sidebar.crop_button.isEnabled()


def test_sidebar_cover_api_emits_style_and_debounced_identity(qapp):
    from provas.motor import Config
    from provas.ui.sidebar import WorkflowSidebar

    sidebar = WorkflowSidebar()
    styles: list[str] = []
    identities: list[dict[str, str]] = []
    sidebar.cover_style_changed.connect(styles.append)
    sidebar.cover_identity_changed.connect(identities.append)

    sidebar.set_cover_style("curvas_editoriais", emit=True)
    sidebar.set_cover_identity(
        Config(".", titulo="Aurora", estudio="Estúdio Fanara", site="fanara.com.br", logo="marca.png")
    )
    sidebar.title_edit.setText("Aurora editorial")
    sidebar.studio_edit.setText("Fanara")
    sidebar.site_edit.setText("fanara.com.br/ensaios")

    assert styles == ["curvas_editoriais"]
    assert identities == []
    deadline = time.perf_counter() + 1.2
    while not identities and time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert identities == [{
        "titulo": "Aurora editorial",
        "estudio": "Fanara",
        "site": "fanara.com.br/ensaios",
        "logo": "marca.png",
    }]


def test_cover_identity_waits_for_typing_pause_before_requesting_preview(qapp):
    from provas.ui.sidebar import WorkflowSidebar

    sidebar = WorkflowSidebar()
    identities: list[dict[str, str]] = []
    sidebar.cover_identity_changed.connect(identities.append)

    for partial_title in ("E", "En", "Ens"):
        sidebar.title_edit.setText(partial_title)
        QTest.qWait(300)

    assert identities == []

    QTest.qWait(850)
    assert [identity["titulo"] for identity in identities] == ["Ens"]


def test_switching_cover_style_rerenders_only_cover_and_preserves_album(
    qapp, tmp_path: Path, plan, monkeypatch
):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    before = window.project_state
    preview_requests: list[bool] = []
    monkeypatch.setattr(window, "request_preview", lambda: preview_requests.append(True))

    window.set_cover_style("curvas_editoriais")

    assert preview_requests == [True]
    assert window.project_state is not None and before is not None
    assert window.project_state.config.estilo_capa == "curvas_editoriais"
    assert window.project_state.plan == before.plan
    assert window.project_state.config.semente == before.config.semente
    assert window.project_state.config.cover_ids == before.config.cover_ids


def test_cover_identity_change_preserves_pages_seed_and_manual_cover(
    qapp, tmp_path: Path, plan, monkeypatch
):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    replacement = plan.pages[-1].photo_ids[-1]
    window.replace_cover_photo(0, replacement)
    before = window.project_state
    preview_requests: list[bool] = []
    monkeypatch.setattr(window, "request_preview", lambda: preview_requests.append(True))

    window.set_cover_identity({
        "titulo": "Ensaio Aurora",
        "estudio": "Estúdio Fanara",
        "site": "fanara.com.br",
        "logo": "logo-inexistente.png",
    })

    assert preview_requests == [True]
    assert window.project_state is not None and before is not None
    assert window.project_state.plan == before.plan
    assert window.project_state.config.semente == before.config.semente
    assert window.project_state.config.cover_ids == before.config.cover_ids
    assert window.project_state.config.titulo == "Ensaio Aurora"
    assert window.project_state.config.logo == "logo-inexistente.png"
    assert window.status_kind == "warning"


def test_unreadable_logo_is_a_non_blocking_portuguese_warning(
    qapp, tmp_path: Path, plan, monkeypatch
):
    from provas.ui import MainWindow

    bad_logo = tmp_path / "logo.png"
    bad_logo.write_bytes(b"imagem invalida")
    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    preview_requests: list[bool] = []
    monkeypatch.setattr(window, "request_preview", lambda: preview_requests.append(True))

    window.set_cover_identity({"logo": str(bad_logo)})

    assert preview_requests == [True]
    assert window.project_state is not None
    assert window.project_state.config.logo == str(bad_logo)
    assert window.status_kind == "warning"
    assert "não pôde ser lido" in window.status_message


def test_cover_warning_survives_preview_completion(qapp, tmp_path: Path, plan):
    from provas.identidade_capa import CoverWarning
    from provas.motor import PreviewResult
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    result = PreviewResult(
        tuple(Image.new("RGB", (420, 297)) for _ in range(len(plan.pages) + 1)),
        (CoverWarning("logo_ilegivel", "O logotipo não pôde ser lido; a capa foi criada sem ele."),),
    )

    window.apply_preview_ready(result)

    assert window.export_button.isEnabled()
    assert window.status_kind == "warning"
    assert window.status_message == "O logotipo não pôde ser lido; a capa foi criada sem ele."


def test_busy_state_disables_all_cover_editing_controls(qapp):
    from provas.ui.sidebar import WorkflowSidebar

    sidebar = WorkflowSidebar()
    sidebar.set_busy(True, "Preparando prévia")

    assert all(not control.isEnabled() for control in (
        sidebar.cover_style,
        sidebar.title_edit,
        sidebar.studio_edit,
        sidebar.site_edit,
        sidebar.logo_choose_button,
        sidebar.logo_remove_button,
    ))


def test_mode_switch_updates_config_and_existing_plan_without_reanalysis(qapp, tmp_path: Path, plan):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)

    window.set_mode("fotolivro")

    assert window.mode == "fotolivro"
    assert window.project_state is not None
    assert window.project_state.plan.mode == "fotolivro"
    assert not window.project_state.config.marca_dagua
    assert not window.project_state.config.mostrar_codigos
    assert "fotolivro limpo" in window.sidebar.mode_description.text().lower()


def test_progress_and_cancel_are_stateful_and_non_blocking(qapp):
    from provas.ui import MainWindow

    window = MainWindow()
    cancel_event = threading.Event()

    window.begin_operation("Analisando fotografias", cancel_event)
    window.update_operation_progress(42, "Lendo D61_0042.jpg")

    assert window.is_busy
    assert window.sidebar.progress_bar.value() == 42
    assert window.sidebar.cancel_button.isEnabled()
    assert "D61_0042" in window.status_message

    started = time.perf_counter()
    window.cancel_active_operation()

    assert cancel_event.is_set()
    assert time.perf_counter() - started < 0.1
    assert "cancelamento" in window.status_message.lower()


def test_ready_state_clears_completed_operation_controls(qapp, tmp_path: Path, plan):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    window.begin_operation("Preparando a prévia…", threading.Event())
    window.update_operation_progress(73, "Renderizando página 2")

    window.apply_preview_ready(tuple(Image.new("RGB", (420, 297)) for _ in plan.pages))

    assert window.sidebar.progress_panel.isHidden()
    assert window.sidebar.progress_bar.value() == 0
    assert window.sidebar.progress_label.text() == ""
    assert not window.sidebar.cancel_button.isEnabled()


def test_preview_ready_populates_roles_and_enables_editing_actions(qapp, tmp_path: Path, plan):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    previews = (
        Image.new("RGB", (420, 297), "#f2f2f2"),
        Image.new("RGB", (420, 297), "#e5e5e5"),
    )

    window.apply_preview_ready(previews)
    qapp.processEvents()

    assert window.preview_grid.thumbnail_count == 2
    assert window.preview_grid.page_roles == ("Abertura", "Encerramento")
    assert window.export_button.isEnabled()
    assert window.sidebar.cover_button.isEnabled()
    assert window.preview_grid.regenerate_button.isEnabled()
    assert "prévia" in window.status_message.lower()


def test_preview_places_cover_before_internal_page_roles(qapp, tmp_path: Path, plan):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    previews = tuple(Image.new("RGB", (420, 297)) for _ in range(len(plan.pages) + 1))

    window.apply_preview_ready(previews)

    assert window.preview_grid.thumbnail_count == len(plan.pages) + 1
    assert window.preview_grid.page_roles == ("Capa", "Abertura", "Encerramento")
    assert window.preview_grid.page_labels[0] == "Capa"


def test_cover_preview_never_reuses_stale_pixels_for_same_plan(qapp, plan):
    from provas.ui.preview_grid import PreviewGrid

    grid = PreviewGrid()
    internal_images = tuple(Image.new("RGB", (420, 297), "white") for _ in plan.pages)
    first = (Image.new("RGB", (420, 297), "red"), *internal_images)
    second = (Image.new("RGB", (420, 297), "blue"), *internal_images)

    grid.set_previews(plan, first)
    grid.set_previews(plan, second)

    assert grid._images[0].pixelColor(1, 1).name() == "#0000ff"


def test_preview_translates_generated_sequence_role(qapp, tmp_path: Path, plan):
    from provas.ui.preview_grid import PreviewGrid

    sequence = replace(
        plan,
        pages=(PagePlan(1, "pair-landscapes", plan.pages[1].photo_ids[:2], "sequence"),),
    )
    grid = PreviewGrid()
    grid.set_previews(sequence, (Image.new("RGB", (420, 297)),))

    assert grid.page_roles == ("Sequência",)


@pytest.fixture
def grid_with_cover(qapp, plan):
    from provas.ui.preview_grid import PreviewGrid

    grid = PreviewGrid()
    grid.resize(760, 560)
    grid.show()
    grid.set_previews(
        plan,
        (
            Image.new("RGB", (420, 297), "#202126"),
            Image.new("RGB", (420, 297), "#D6E5F2"),
            Image.new("RGB", (420, 297), "#EBD9C9"),
        ),
    )
    grid.set_page_alternatives({1})
    for _ in range(3):
        qapp.processEvents()
    yield grid
    grid.close()


def test_only_internal_pages_with_alternatives_have_reload_button(grid_with_cover):
    assert grid_with_cover.card(0).reload_button is None
    assert grid_with_cover.card(1).reload_button.isVisible()
    assert grid_with_cover.card(1).reload_button.isEnabled()
    assert grid_with_cover.card(1).reload_button.size().toTuple() == (28, 28)
    assert not grid_with_cover.card(2).reload_button.isEnabled()


def test_reload_button_emits_its_page_number_and_has_clear_accessibility(grid_with_cover, qapp):
    button = grid_with_cover.card(1).reload_button
    assert button is not None
    assert button.accessibleName() == "Mudar diagramação da página 1"
    assert button.toolTip() == "Mudar diagramação da página 1"
    emitted: list[int] = []
    grid_with_cover.page_layout_requested.connect(emitted.append)

    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    qapp.processEvents()

    assert button.hasFocus()
    assert emitted == [1]


def test_page_reload_busy_state_is_discrete_and_disables_its_button(grid_with_cover):
    button = grid_with_cover.card(1).reload_button
    assert button is not None

    grid_with_cover.set_page_busy(1, True)

    assert not button.isEnabled()
    assert button.text() == "…"
    assert button.property("busy") is True
    assert button.accessibleDescription() == "Atualizando diagramação da página 1"

    grid_with_cover.set_page_busy(1, False)

    assert button.isEnabled()
    assert button.text() == "↻"
    assert button.property("busy") is False


def test_replace_page_preview_keeps_card_scroll_and_lru_entry(qapp, tmp_path: Path, plan):
    from provas.ui.preview_grid import PreviewGrid

    pages = tuple(
        PagePlan(number, "solo-landscape", (str(tmp_path / f"page-{number}.jpg"),), "narrative")
        for number in range(1, 15)
    )
    full_plan = replace(plan, pages=pages)
    images = tuple(Image.new("RGB", (420, 297), "#D6E5F2") for _ in pages)
    grid = PreviewGrid()
    grid.resize(760, 480)
    grid.show()
    grid.set_previews(full_plan, images)
    grid.set_zoom(120)
    for _ in range(4):
        qapp.processEvents()
    scrollbar = grid.scroll_area.verticalScrollBar()
    scrollbar.setValue(min(40, scrollbar.maximum()))
    original_scroll = scrollbar.value()
    card = grid.card(1)
    original_geometry = card.geometry()
    materialized_before = grid.materialized_thumbnail_count
    replacement = Image.new("RGB", (420, 297), "#D84A68")

    grid.replace_page_preview(1, replacement)

    cache_key = (full_plan.seed, full_plan.mode, 1, pages[0].template_id, pages[0].photo_ids)
    assert grid.card(1) is card
    assert card.geometry() == original_geometry
    assert scrollbar.value() == original_scroll
    assert grid.zoom == 120
    assert grid.materialized_thumbnail_count == materialized_before
    assert grid._images[0].pixelColor(1, 1).name() == "#d84a68"
    assert grid._pixmap_cache[cache_key].pixelColor(1, 1).name() == "#d84a68"
    grid.close()


def test_ready_hierarchy_keeps_export_as_the_only_primary_action(qapp, tmp_path: Path, plan):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    window.apply_preview_ready(tuple(Image.new("RGB", (420, 297)) for _ in plan.pages))

    assert window.sidebar.folder_button.text() == "Trocar pasta"
    assert window.sidebar.folder_button.objectName() == "secondaryButton"
    assert window.export_button.objectName() == "primaryButton"


def test_cover_replacement_keeps_slot_order_and_survives_regeneration(qapp, tmp_path: Path, plan):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    replacement = plan.pages[-1].photo_ids[-1]

    window.replace_cover_photo(0, replacement)

    assert window.project_state is not None
    assert window.project_state.plan.cover_photo_ids == (replacement, plan.cover_photo_ids[1])
    assert window.project_state.config.cover_ids == (replacement, plan.cover_photo_ids[1])

    alternate = replace(plan, seed=8, cover_photo_ids=())
    window.apply_regenerated_plan(alternate)

    assert window.project_state.plan.cover_photo_ids == (replacement, plan.cover_photo_ids[1])


def test_classic_cover_photo_is_independent_and_requests_one_preview(
    qapp, tmp_path: Path, plan, monkeypatch
):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    replacement = plan.pages[-1].photo_ids[1]
    window.replace_cover_photo(0, plan.pages[-1].photo_ids[-1])
    previous_plan = replace(plan, seed=plan.seed - 1)
    window.project_state = replace(window.project_state, previous_plan=previous_plan)
    before = window.project_state
    preview_requests: list[bool] = []
    monkeypatch.setattr(window, "request_preview", lambda: preview_requests.append(True))

    window.set_classic_cover_photo(replacement)

    assert window.project_state is not None and before is not None
    assert window.project_state.config.foto_capa_id == replacement
    assert window.project_state.config.cover_ids == before.config.cover_ids
    assert window.project_state.plan == before.plan
    assert window.project_state.previous_plan == previous_plan
    assert window.project_state.config.semente == before.config.semente
    assert window.project_state.config.capa_enquadramento == "automatico"
    assert preview_requests == [True]


def test_classic_crop_changes_only_cover_config_and_requests_one_preview(
    qapp, tmp_path: Path, plan, monkeypatch
):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    window.project_state = replace(
        window.project_state,
        previous_plan=replace(plan, seed=plan.seed - 1),
    )
    before = window.project_state
    preview_requests: list[bool] = []
    monkeypatch.setattr(window, "request_preview", lambda: preview_requests.append(True))

    window.set_classic_crop(0.22, 0.78, 1.85)

    assert window.project_state is not None and before is not None
    assert (
        window.project_state.config.capa_foco_x,
        window.project_state.config.capa_foco_y,
        window.project_state.config.capa_zoom,
        window.project_state.config.capa_enquadramento,
    ) == (0.22, 0.78, 1.85, "manual")
    assert window.project_state.plan == before.plan
    assert window.project_state.previous_plan == before.previous_plan
    assert window.project_state.config.semente == before.config.semente
    assert window.project_state.config.cover_ids == before.config.cover_ids
    assert window.previews == ()
    assert preview_requests == [True]


def test_regeneration_can_be_undone_and_preserves_scroll(qapp, tmp_path: Path, plan):
    from provas.ui import MainWindow

    pages = tuple(
        PagePlan(
            number,
            "solo-landscape",
            (str(tmp_path / f"page-{number}.jpg"),),
            "opening" if number == 1 else "ending" if number == 14 else "narrative",
        )
        for number in range(1, 15)
    )
    plan = replace(plan, pages=pages)
    window = MainWindow()
    window.resize(1000, 640)
    window.show()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    window.apply_preview_ready(tuple(Image.new("RGB", (420, 297)) for _ in plan.pages))
    for _ in range(3):
        qapp.processEvents()
    assert window.preview_grid.scroll_area.verticalScrollBar().maximum() >= 19
    window.preview_grid.scroll_area.verticalScrollBar().setValue(19)
    alternate = replace(plan, seed=plan.seed + 1)

    window.apply_regenerated_plan(alternate)

    assert window.project_state is not None
    assert window.project_state.plan == alternate
    assert window.preview_grid.undo_button.isEnabled()

    window.hide()
    window.undo_regeneration()

    assert window.project_state.plan == plan
    assert not window.preview_grid.undo_button.isEnabled()
    assert window.preview_grid.pending_scroll_position == 19


def test_export_success_failure_and_empty_states_are_actionable_in_portuguese(
    qapp, tmp_path: Path, plan
):
    from provas.ui import MainWindow

    window = MainWindow()
    assert "escolher pasta" in window.preview_grid.empty_message.lower()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    output = tmp_path / "fotolivro.pdf"

    window.apply_export_success(Resultado(str(output), 4, 2))

    assert window.last_export_path == str(output)
    assert "exportado" in window.status_message.lower()
    assert window.status_kind == "success"

    window.apply_failure("Nenhuma fotografia encontrada")

    assert "não foi possível" in window.status_message.lower()
    assert "tente novamente" in window.status_message.lower()
    assert window.status_kind == "error"


def test_recoverable_analysis_failures_reach_editorial_diagnostics(qapp, tmp_path: Path, plan):
    from provas.modelos import PhotoInfo
    from provas.ui import MainWindow

    photo = PhotoInfo(
        id=plan.pages[0].photo_ids[0],
        path=plan.pages[0].photo_ids[0],
        label="D61_0001",
        width=200,
        height=300,
        index=0,
    )
    failures = (("corrompida.jpg", "arquivo JPEG inválido"),)
    window = MainWindow()
    window.select_folder(str(tmp_path))

    window.apply_analysis_result(plan, photos=(photo,), failures=failures)

    assert window.diagnostics.failed_count == 1
    assert "corrompida.jpg" in window.diagnostics.warnings_label.text()
    assert "JPEG inválido" in window.diagnostics.warnings_label.toolTip()


def test_workers_publish_uniform_signals_and_honor_cancellation(qapp, tmp_path: Path, plan):
    from provas.ui import AnalysisWorker, ExportWorker, PreviewWorker

    progress = []
    completed = []

    def analyze(config, progresso, cancelar):
        progresso(2, 4, "Analisando fotografia")
        return plan

    worker = AnalysisWorker(Config(str(tmp_path)), operation=analyze)
    worker.progress.connect(lambda percent, message: progress.append((percent, message)))
    worker.completed.connect(completed.append)
    worker.run()
    worker.run()

    assert progress == [(50, "Analisando fotografia")]
    assert completed == [plan]
    assert all(hasattr(worker, name) for name in ("progress", "completed", "failed", "cancelled"))

    cancelled = []
    cancel_event = threading.Event()
    cancel_event.set()
    preview_worker = PreviewWorker(
        Config(str(tmp_path)), plan, cancel_event=cancel_event,
        operation=lambda *_args, **_kwargs: (),
    )
    preview_worker.cancelled.connect(lambda: cancelled.append(True))
    preview_worker.run()

    assert cancelled == [True]
    assert all(
        hasattr(ExportWorker(Config(str(tmp_path)), plan), name)
        for name in ("progress", "completed", "failed", "cancelled")
    )


def test_page_cycle_worker_emits_result_and_never_completes_after_cancellation(qapp, tmp_path: Path, plan):
    from provas import motor
    from provas.ui.workers import PageCycleWorker

    completed = []
    cancelled = []
    calls = []
    cancel_event = threading.Event()
    result = object()

    def operation(config, supplied_plan, page_number, preview_width, *, cancelar):
        calls.append((config, supplied_plan, page_number, preview_width, cancelar))
        cancel_event.set()
        return result

    worker = PageCycleWorker(
        Config(str(tmp_path)), plan, 1, 720, cancel_event=cancel_event, operation=operation,
    )
    worker.completed.connect(completed.append)
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.run()

    assert calls == [(worker.config, plan, 1, 720, cancel_event)]
    assert completed == []
    assert cancelled == [True]


def test_page_cycle_worker_reports_failures_in_portuguese(qapp, tmp_path: Path, plan):
    from provas.ui.workers import PageCycleWorker

    failures = []

    def operation(*_args, **_kwargs):
        raise OSError("arquivo de imagem ilegível")

    worker = PageCycleWorker(Config(str(tmp_path)), plan, 1, 420, operation=operation)
    worker.failed.connect(failures.append)
    worker.run()

    assert failures == ["Não foi possível atualizar a página: arquivo de imagem ilegível"]


def test_page_cycle_worker_cancellation_wins_at_the_prepublication_boundary(qapp, tmp_path: Path, plan, monkeypatch):
    from provas.ui.workers import PageCycleWorker

    completed = []
    cancelled = []
    result = object()
    worker = PageCycleWorker(
        Config(str(tmp_path)), plan, 1, 420, operation=lambda *_args, **_kwargs: result,
    )
    original_is_cancelled = worker._is_cancelled
    checks = 0

    def cancel_immediately_before_publication() -> bool:
        nonlocal checks
        checks += 1
        if checks == 2:
            worker.cancel()
            return False
        return original_is_cancelled()

    monkeypatch.setattr(worker, "_is_cancelled", cancel_immediately_before_publication)
    worker.completed.connect(completed.append)
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.run()

    assert worker.cancel_event.is_set()
    assert completed == []
    assert cancelled == [True]


def test_worker_emits_terminal_signal_after_releasing_its_terminal_lock(qapp, tmp_path: Path, plan):
    from provas.ui.workers import PageCycleWorker

    worker = PageCycleWorker(
        Config(str(tmp_path)), plan, 1, 420, operation=lambda *_args, **_kwargs: object(),
    )
    lock_available = []

    def observe_terminal_signal() -> None:
        def attempt_lock() -> None:
            acquired = worker._terminal_lock.acquire(timeout=0.1)
            lock_available.append(acquired)
            if acquired:
                worker._terminal_lock.release()

        observer = threading.Thread(target=attempt_lock)
        observer.start()
        observer.join(timeout=1)
        assert not observer.is_alive()

    worker.completed.connect(observe_terminal_signal)
    worker.run()

    assert lock_available == [True]


def test_main_window_delegates_active_cancellation_to_workers_before_setting_shared_event(qapp):
    from provas.ui import MainWindow

    class ProbeWorker:
        def __init__(self, event: threading.Event) -> None:
            self.event = event
            self.event_was_already_set = None

        def cancel(self) -> None:
            self.event_was_already_set = self.event.is_set()
            self.event.set()

    window = MainWindow()
    event = threading.Event()
    worker = ProbeWorker(event)
    window._cancel_event = event
    window._workers = {worker}

    window.cancel_active_operation()

    assert worker.event_was_already_set is False
    assert event.is_set()
    window.close()


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        (ValueError("Thumbnail width must be positive"), "a largura da prévia deve ser maior que zero"),
        (ValueError("Unknown template: legado"), "o layout desta página não é reconhecido"),
        (ValueError("Unknown page number: 17"), "a página solicitada não existe no plano"),
        (ValueError("Missing preview assets: imagem.jpg"), "faltam fotos necessárias para renderizar esta página"),
    ),
)
def test_page_cycle_worker_translates_known_internal_errors_to_portuguese(
    qapp, tmp_path: Path, plan, error: ValueError, expected: str,
):
    from provas.ui.workers import PageCycleWorker

    failures = []
    worker = PageCycleWorker(
        Config(str(tmp_path)), plan, 1, 420,
        operation=lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )
    worker.failed.connect(failures.append)
    worker.run()

    assert failures == [f"Não foi possível atualizar a página: {expected}."]
    assert "Thumbnail width" not in failures[0]
    assert "Unknown template" not in failures[0]


def test_page_cycle_queue_serializes_requests_ignores_duplicates_and_locks_global_actions(
    qapp, plan, monkeypatch,
):
    from provas.ui import MainWindow

    three_pages = replace(
        plan,
        pages=(
            *plan.pages,
            PagePlan(3, "single-full", (plan.pages[0].photo_ids[0],), "ending"),
        ),
    )
    window = MainWindow()
    window.apply_analysis_result(three_pages)
    window.previews = (object(),)
    started: list[int] = []

    def start(page_number: int) -> None:
        started.append(page_number)
        window._page_cycle_worker = type("Worker", (), {"page_number": page_number})()  # type: ignore[assignment]

    monkeypatch.setattr(window, "_start_page_cycle_worker", start)

    window.request_page_cycle(1)
    window.request_page_cycle(1)
    window.request_page_cycle(2)
    window.request_page_cycle(3)

    assert started == [1]
    assert tuple(window._page_cycle_queue) == (2, 3)
    assert window._page_cycle_busy == {1, 2, 3}
    assert window.is_busy
    assert not window.open_project_button.isEnabled()
    assert not window.save_button.isEnabled()
    assert not window.sidebar.folder_button.isEnabled()
    assert not window.sidebar.proof_radio.isEnabled()
    assert not window.sidebar.book_radio.isEnabled()
    assert not window.sidebar.cover_style.isEnabled()
    assert not window.sidebar.title_edit.isEnabled()
    assert not window.sidebar.logo_choose_button.isEnabled()
    assert window.preview_grid.zoom_in_button.isEnabled()


def test_page_cycle_failure_releases_its_button_and_continues_the_queue(qapp, plan, monkeypatch):
    from provas.ui import MainWindow

    window = MainWindow()
    window.apply_analysis_result(plan)
    previews = (object(),)
    window.previews = previews
    started: list[int] = []

    def start(page_number: int) -> None:
        started.append(page_number)
        window._page_cycle_worker = type("Worker", (), {"page_number": page_number})()  # type: ignore[assignment]

    monkeypatch.setattr(window, "_start_page_cycle_worker", start)
    window.request_page_cycle(1)
    window.request_page_cycle(2)
    window._page_cycle_failed("falha simulada")

    assert started == [1, 2]
    assert window._page_cycle_busy == {2}
    assert window.status_kind == "error"
    assert "falha simulada" in window.status_message


def test_page_cycle_cancellation_clears_pending_pages_and_restores_global_actions(qapp, plan):
    from provas.ui import MainWindow

    window = MainWindow()
    window.apply_analysis_result(plan)
    previews = (object(),)
    window.previews = previews
    window.is_busy = True
    window._cancel_event = threading.Event()
    window._page_cycle_worker = type("Worker", (), {"page_number": 1})()  # type: ignore[assignment]
    window._page_cycle_busy = {1, 2}
    window._page_cycle_queue.extend((2,))

    window._page_cycle_cancelled()

    assert not window.is_busy
    assert window._page_cycle_busy == set()
    assert not window._page_cycle_queue
    assert window.open_project_button.isEnabled()
    assert window.status_kind == "idle"


def test_page_cycle_defers_a_pending_cover_identity_until_the_queue_finishes(
    qapp, plan, monkeypatch,
):
    from provas.ui import MainWindow

    window = MainWindow()
    window.apply_analysis_result(plan)
    previews = (object(),)
    window.previews = previews
    requested_previews: list[bool] = []
    monkeypatch.setattr(window, "request_preview", lambda: requested_previews.append(True))

    def start(page_number: int) -> None:
        window._page_cycle_worker = type("Worker", (), {"page_number": page_number})()  # type: ignore[assignment]

    monkeypatch.setattr(window, "_start_page_cycle_worker", start)
    window.request_page_cycle(1)
    window.set_cover_identity({"titulo": "Depois da fila"})

    assert window.project_state is not None
    assert window.project_state.config.titulo != "Depois da fila"
    assert window.previews is previews
    assert requested_previews == []

    window._page_cycle_cancelled()

    assert window.project_state.config.titulo == "Depois da fila"
    assert requested_previews == [True]


def test_page_cycle_blocks_choose_folder_shortcut_handler(qapp, plan, monkeypatch):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder("pasta-original")
    window.apply_analysis_result(plan)
    window.previews = (object(),)

    def start(page_number: int) -> None:
        window._page_cycle_worker = type("Worker", (), {"page_number": page_number})()  # type: ignore[assignment]

    monkeypatch.setattr(window, "_start_page_cycle_worker", start)
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args: pytest.fail("O seletor de pasta não deve abrir durante a fila."),
    )
    window.request_page_cycle(1)
    window.choose_folder()

    assert window.folder_path.endswith("pasta-original")


def test_page_cycle_shutdown_discards_deferred_identity_without_starting_preview(
    qapp, plan, monkeypatch,
):
    from provas.ui import MainWindow

    window = MainWindow()
    window.apply_analysis_result(plan)
    window.previews = (object(),)

    def start(page_number: int) -> None:
        window._page_cycle_worker = type("Worker", (), {"page_number": page_number})()  # type: ignore[assignment]

    monkeypatch.setattr(window, "_start_page_cycle_worker", start)
    monkeypatch.setattr(
        window,
        "request_preview",
        lambda: pytest.fail("O fechamento não deve iniciar uma prévia nova."),
    )
    window.request_page_cycle(1)
    window.set_cover_identity({"titulo": "Não iniciar no fechamento"})
    window.request_shutdown()

    window._page_cycle_cancelled()

    assert window._deferred_cover_identity is None


def test_page_cycle_result_updates_only_its_plan_and_thumbnail(qapp, plan):
    from provas.motor import PageCycleResult
    from provas.ui import MainWindow

    window = MainWindow()
    window.apply_analysis_result(plan)
    previews = tuple(Image.new("RGB", (420, 297), "#d6e5f2") for _ in plan.pages)
    window.previews = previews
    window.preview_grid.set_previews(plan, previews)
    card = window.preview_grid.card(1)
    cycled = replace(
        plan,
        pages=(replace(plan.pages[0], template_id="single-full"), plan.pages[1]),
    )
    window._page_cycle_worker = type("Worker", (), {"page_number": 1})()  # type: ignore[assignment]
    window._page_cycle_busy = {1}

    window._page_cycle_completed(
        PageCycleResult(cycled, 1, Image.new("RGB", (420, 297), "#d84a68"))
    )

    assert window.project_state is not None
    assert window.project_state.plan == cycled
    assert window.project_state.plan.pages[1] == plan.pages[1]
    assert window.preview_grid.card(1) is card
    assert window.preview_grid._plan == cycled
    assert window.preview_grid._images[0].pixelColor(1, 1).name() == "#d84a68"


def test_page_cycle_result_can_be_saved_and_reopened(qapp, tmp_path: Path):
    from provas.ciclo_paginas import ciclar_pagina
    from provas.compositor import compose
    from provas.modelos import PhotoInfo
    from provas.motor import PageCycleResult
    from provas.projeto import load_project, save_project
    from provas.ui import MainWindow

    photos = tuple(
        PhotoInfo(
            id=str(tmp_path / f"foto-{number}.jpg"), path=str(tmp_path / f"foto-{number}.jpg"),
            label=f"Foto {number}", width=300, height=450, index=number,
            sharpness=0.7, exposure=0.7, density=0.6, quality=0.8, similarity_group=number,
        )
        for number in range(17)
    )
    plan = compose(photos, "fotolivro", 41)
    ratios = {photo.id: photo.width / photo.height for photo in photos}
    page_number = next(
        page.number for page in plan.pages
        if ciclar_pagina(plan, page.number, ratios) != plan
    )
    cycled = ciclar_pagina(plan, page_number, ratios)
    window = MainWindow()
    window.apply_analysis_result(plan, photos=photos)
    previews = tuple(Image.new("RGB", (420, 297), "#d6e5f2") for _ in plan.pages)
    window.previews = previews
    window.preview_grid.set_previews(plan, previews)
    window._page_cycle_worker = type("Worker", (), {"page_number": page_number})()  # type: ignore[assignment]
    window._page_cycle_busy = {page_number}

    window._page_cycle_completed(
        PageCycleResult(cycled, page_number, Image.new("RGB", (420, 297), "#d84a68"))
    )

    destination = tmp_path / "pagina-ciclada.provas.json"
    assert window.project_state is not None
    save_project(destination, window.project_state)
    assert load_project(destination).plan == cycled


def test_page_cycle_click_runs_worker_and_keeps_preview_interactions_available(qapp, plan):
    from provas.ui import MainWindow

    for index, photo_id in enumerate(
        photo_id for page in plan.pages for photo_id in page.photo_ids
    ):
        Image.new("RGB", (600, 400), (80 + index * 20, 90, 100)).save(photo_id)
    window = MainWindow()
    window.apply_analysis_result(plan)
    previews = tuple(Image.new("RGB", (420, 297), "#d6e5f2") for _ in plan.pages)
    window.previews = previews
    window.preview_grid.set_previews(plan, previews)
    original = window.project_state.plan

    window.preview_grid.page_layout_requested.emit(1)
    deadline = time.monotonic() + 10
    while window.is_busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert not window.is_busy
    assert window.project_state is not None
    assert window.project_state.plan.pages[0] != original.pages[0]
    assert window.preview_grid.zoom_in_button.isEnabled()
    window.close()


def test_close_waits_for_active_page_cycle_thread_to_stop(qapp, tmp_path: Path, plan, monkeypatch):
    from provas import motor
    from provas.ui import MainWindow
    from provas.ui import main_window
    from provas.ui.workers import PageCycleWorker

    def cooperative_operation(_config, _plan, _number, _width, *, cancelar):
        while not cancelar.is_set():
            time.sleep(0.002)
        raise motor.Cancelado()

    class SlowPageCycleWorker(PageCycleWorker):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, operation=cooperative_operation, **kwargs)

    monkeypatch.setattr(main_window, "PageCycleWorker", SlowPageCycleWorker)
    window = MainWindow()
    window.show()
    window.apply_analysis_result(plan)
    window.previews = (object(),)
    window.request_page_cycle(1)
    for _ in range(3):
        qapp.processEvents()

    window.close()

    deadline = time.perf_counter() + 2
    while window.isVisible() and time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert not window.isVisible()
    assert not window._threads
    assert window._page_cycle_thread is None


def test_resize_hides_diagnostics_before_sacrificing_preview(qapp):
    from provas.ui import MainWindow

    window = MainWindow()
    window.resize(1000, 700)
    window.show()
    qapp.processEvents()
    assert window.diagnostics.isHidden()

    window.resize(1366, 768)
    qapp.processEvents()
    assert window.diagnostics.isVisible()
    assert window.preview_grid.width() > window.sidebar.width()
    window.close()


def test_1366_by_768_at_125_percent_fits_logical_work_area(qapp):
    from provas.ui import MainWindow

    logical_width = round(1366 / 1.25)
    logical_height = round(768 / 1.25)
    window = MainWindow()
    window.resize(logical_width, logical_height)
    window.show()
    for _ in range(3):
        qapp.processEvents()

    assert window.size().width() == logical_width
    assert window.size().height() == logical_height
    assert window.minimumHeight() <= logical_height
    assert window.diagnostics.isHidden()
    scroll = window.sidebar.scroll_area
    scroll.ensureWidgetVisible(window.sidebar.cover_button)
    qapp.processEvents()
    button_rect = window.sidebar.cover_button.rect()
    top_left = window.sidebar.cover_button.mapTo(scroll.viewport(), button_rect.topLeft())
    bottom_right = window.sidebar.cover_button.mapTo(scroll.viewport(), button_rect.bottomRight())
    assert top_left.y() >= 0
    assert bottom_right.y() < scroll.viewport().height()
    assert window.export_button.geometry().bottom() <= window.top_bar.height()
    window.close()


def test_sidebar_controls_remain_reachable_at_minimum_window_size(qapp):
    from provas.ui import MainWindow

    window = MainWindow()
    window.resize(840, 540)
    window.show()
    for _ in range(3):
        qapp.processEvents()

    scroll = window.sidebar.scroll_area
    assert scroll.verticalScrollBar().maximum() > 0
    for control in (window.sidebar.cover_style, window.sidebar.site_edit, window.sidebar.cover_button):
        scroll.ensureWidgetVisible(control)
        qapp.processEvents()
        top = control.mapTo(scroll.viewport(), control.rect().topLeft()).y()
        bottom = control.mapTo(scroll.viewport(), control.rect().bottomRight()).y()
        assert 0 <= top < bottom < scroll.viewport().height()
    assert window.preview_grid.width() > window.sidebar.width()
    window.close()


def test_scrolled_cover_section_starts_cleanly_at_logical_125_percent_size(qapp):
    from provas.ui import MainWindow

    window = MainWindow()
    window.resize(1093, 614)
    window.show()
    qapp.processEvents()
    scroll = window.sidebar.scroll_area
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    qapp.processEvents()

    top = window.sidebar.cover_section_label.mapTo(
        scroll.viewport(), window.sidebar.cover_section_label.rect().topLeft()
    ).y()
    assert 0 <= top <= 40
    window.close()


def test_zoomed_out_narrow_grid_never_clips_a_thumbnail(qapp, tmp_path: Path):
    from provas.ui import MainWindow

    pages = tuple(
        PagePlan(number, "solo-landscape", (str(tmp_path / f"{number}.jpg"),), "narrative")
        for number in range(1, 7)
    )
    plan = BookPlan(4, "prova", (), pages)
    window = MainWindow()
    window.resize(913, 640)
    window.show()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    window.apply_preview_ready(tuple(Image.new("RGB", (420, 297)) for _ in pages))
    window.preview_grid.set_zoom(60)
    for _ in range(4):
        qapp.processEvents()

    grid = window.preview_grid
    right_margin = grid.grid.contentsMargins().right()
    first_row = grid._cards[:grid._laid_out_columns]
    assert grid.content.width() <= grid.scroll_area.viewport().width()
    assert first_row[-1].geometry().right() + right_margin <= grid.scroll_area.viewport().width()
    window.close()


def test_thumbnail_pixmaps_materialize_only_when_cards_intersect_viewport(qapp, tmp_path: Path):
    from provas.ui import MainWindow

    pages = tuple(
        PagePlan(number, "single-landscape", (str(tmp_path / f"lazy-{number}.jpg"),), "narrative")
        for number in range(1, 31)
    )
    plan = BookPlan(4, "prova", (), pages)
    window = MainWindow()
    window.resize(920, 560)
    window.show()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    window.apply_preview_ready(tuple(Image.new("RGB", (420, 297)) for _ in pages))
    for _ in range(4):
        qapp.processEvents()

    initially_loaded = window.preview_grid.materialized_thumbnail_count
    assert 0 < initially_loaded < len(pages)

    scrollbar = window.preview_grid.scroll_area.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    for _ in range(4):
        qapp.processEvents()

    assert initially_loaded < window.preview_grid.materialized_thumbnail_count < len(pages)
    window.close()


def test_minimum_geometry_keeps_preview_and_export_clear_with_long_status(qapp):
    from provas.ui import MainWindow

    window = MainWindow()
    window.resize(860, 640)
    window.set_status(
        "Não foi possível concluir a exportação porque a pasta de destino não está disponível. "
        "Verifique a pasta e tente novamente.",
        "error",
    )
    window.show()
    for _ in range(3):
        qapp.processEvents()

    assert window.size().width() == 860
    assert window.diagnostics.isHidden()
    assert window.preview_grid.width() >= 560
    assert window.status_label.geometry().right() < window.open_project_button.geometry().left()
    assert window.open_project_button.geometry().right() < window.save_button.geometry().left()
    assert window.save_button.geometry().right() < window.export_button.geometry().left()
    assert window.export_button.geometry().right() <= window.top_bar.contentsRect().right()
    assert window.export_button.height() >= 44
    assert window.status_label.toolTip() == window.status_message
    assert window.status_label.text() != window.status_message
    window.close()


def test_theme_text_tokens_meet_wcag_contrast():
    qss = (Path(__file__).parents[1] / "provas" / "ui" / "theme.qss").read_text(encoding="utf-8")
    normal = _qss_property(
        qss, "QPushButton#primaryButton, QPushButton#importantButton", "background"
    )
    hover = _qss_property(
        qss,
        "QPushButton#primaryButton:hover, QPushButton#importantButton:hover",
        "background",
    )
    brand = _qss_property(qss, "QLabel#brandMark", "background")
    loading_text = _qss_property(qss, "QLabel#pageImage", "color")
    loading_background = _qss_property(qss, "QLabel#pageImage", "background")

    assert _contrast_ratio("#FFFFFF", normal) >= 4.5
    assert _contrast_ratio("#FFFFFF", hover) >= 4.5
    assert _contrast_ratio("#FFFFFF", brand) >= 4.5
    assert _contrast_ratio(loading_text, loading_background) >= 4.5


def test_cover_dialog_and_qualitative_diagnostic_use_semantic_text_roles(qapp, plan):
    from provas.ui import CoverDialog, DiagnosticsPanel

    dialog = CoverDialog(plan.cover_photo_ids, plan.pages[-1].photo_ids)
    headings = [label.text() for label in dialog.findChildren(QLabel) if label.objectName() == "sectionTitle"]
    diagnostics = DiagnosticsPanel()

    assert headings == ["Na capa", "Fotografias disponíveis"]
    assert diagnostics.order_value.objectName() == "metricTextValue"


def test_cover_dialog_loads_visible_photo_thumbnails(qapp, image_factory):
    from provas.ui import CoverDialog

    selected = tuple(str(image_factory(f"selecionada-{index}.jpg")) for index in range(2))
    remaining = tuple(str(image_factory(f"disponivel-{index}.jpg")) for index in range(4))
    dialog = CoverDialog(selected, remaining)
    dialog.show()
    for _ in range(4):
        qapp.processEvents()

    assert dialog.selected_list.loaded_thumbnail_count > 0
    assert dialog.remaining_list.loaded_thumbnail_count > 0
    assert not dialog.selected_list.item(0).icon().isNull()
    assert not dialog.remaining_list.item(0).icon().isNull()
    dialog.close()


def test_cover_dialog_single_selection_needs_no_cover_slot(qapp, image_factory):
    from provas.ui import CoverDialog

    current = str(image_factory("atual.jpg", size=(420, 280)))
    alternatives = tuple(
        str(image_factory(f"alternativa-{index}.jpg", size=(420, 280))) for index in range(2)
    )
    dialog = CoverDialog((current,), alternatives, single_selection=True)
    selected: list[str] = []
    dialog.single_photo_selected.connect(selected.append)
    dialog.show()
    qapp.processEvents()

    assert "Escolha a fotografia da capa" in dialog.intro_label.text()
    assert dialog.selected_list.isHidden()
    dialog.remaining_list.setCurrentRow(dialog.remaining_list.count() - 1)
    assert dialog.replace_button.isEnabled()
    dialog.replace_button.click()
    dialog.replace_button.click()

    assert selected == [alternatives[-1]]


def test_cover_dialog_premature_double_click_does_not_consume_valid_multi_selection(
    qapp, image_factory
):
    from provas.ui import CoverDialog

    selected = tuple(str(image_factory(f"slot-{index}.jpg")) for index in range(2))
    remaining = (str(image_factory("nova.jpg")),)
    dialog = CoverDialog(selected, remaining)
    replacements: list[tuple[int, str]] = []
    dialog.replacement_requested.connect(
        lambda slot, photo_id: replacements.append((slot, photo_id))
    )
    dialog.show()
    qapp.processEvents()

    dialog.selected_list.setCurrentRow(-1)
    dialog.remaining_list.setCurrentRow(0)
    dialog.remaining_list.itemDoubleClicked.emit(dialog.remaining_list.item(0))
    dialog.selected_list.setCurrentRow(1)
    dialog.replace_button.click()

    assert replacements == [(1, remaining[0])]


def _drag_crop(canvas, dx: int, dy: int, qapp) -> None:
    start = canvas.rect().center()
    end = start + QPoint(dx, dy)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, end, delay=5)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    qapp.processEvents()


def test_crop_cancel_keeps_committed_value_transactional(qapp, image_factory):
    from provas.capa_classica import ClassicCrop, classic_photo_target
    from provas.ui.crop_dialog import CropDialog

    path = str(image_factory("crop-cancel.jpg", size=(1200, 800)))
    before = ClassicCrop(0.5, 0.5, 1.35, "manual")
    dialog = CropDialog(path, before, classic_photo_target(1754, 1240))
    applied: list[tuple[float, float, float]] = []
    dialog.applied.connect(lambda x, y, zoom: applied.append((x, y, zoom)))
    dialog.show()
    qapp.processEvents()

    _drag_crop(dialog.canvas, 80, -30, qapp)
    assert dialog.value != before
    dialog.reject()

    assert dialog.committed_value == before
    assert applied == []


def test_crop_apply_emits_once_and_commits_bounded_draft(qapp, image_factory):
    from provas.capa_classica import ClassicCrop, classic_photo_target, crop_box
    from provas.ui.crop_dialog import CropDialog

    path = str(image_factory("crop-apply.jpg", size=(900, 1400)))
    before = ClassicCrop()
    target = classic_photo_target(1754, 1240)
    dialog = CropDialog(path, before, target)
    applied: list[tuple[float, float, float]] = []
    dialog.applied.connect(lambda x, y, zoom: applied.append((x, y, zoom)))
    dialog.show()
    qapp.processEvents()

    dialog.zoom_slider.setValue(250)
    _drag_crop(dialog.canvas, -500, 500, qapp)
    box = crop_box(dialog.canvas.source_size, target, dialog.value)
    width, height = dialog.canvas.source_size
    assert 0 <= box.left < box.right <= width
    assert 0 <= box.top < box.bottom <= height
    dialog.apply_button.click()
    dialog.apply_button.click()

    assert len(applied) == 1
    assert applied[0][2] == 2.5
    assert dialog.committed_value == dialog.value


def test_crop_automatic_reset_is_local_until_apply(qapp, image_factory):
    from provas.capa_classica import ClassicCrop, classic_photo_target
    from provas.ui.crop_dialog import CropDialog

    path = str(image_factory("crop-reset.jpg", size=(1200, 800)))
    before = ClassicCrop(0.25, 0.7, 2.0, "manual")
    dialog = CropDialog(path, before, classic_photo_target(1754, 1240))
    dialog.show()
    qapp.processEvents()

    dialog.automatic_button.click()

    assert dialog.value == ClassicCrop(0.5, 0.5, 1.0, "automatico")
    assert dialog.committed_value == before
    assert dialog.zoom_slider.value() == 100
    assert dialog.zoom_label.text() == "100%"
    dialog.reject()
    assert dialog.committed_value == before


def test_crop_canvas_uses_exact_preview_target_for_renderer_source_box(
    qapp, image_factory, monkeypatch
):
    from provas.capa_classica import ClassicCrop, resolve_classic_crop_box
    from provas.ui.crop_dialog import CropDialog

    path = str(image_factory("crop-target.jpg", size=(900, 1400)))
    target = (1473, 904)
    crop = ClassicCrop(0.32, 0.72, 1.6, "manual")
    monkeypatch.setattr("provas.ui.crop_dialog.enquadramento.detect_faces", lambda _image: ())

    dialog = CropDialog(path, crop, target)

    assert dialog.canvas.target_size == target
    assert dialog.canvas.source_box == resolve_classic_crop_box(
        dialog.canvas.source_size,
        target,
        crop,
        (),
    )


def test_classic_crop_applies_preview_photo_atomically_when_new_crop_would_rerank(
    qapp, tmp_path: Path, image_factory, monkeypatch
):
    from provas import capas
    from provas.capa_classica import ClassicCrop
    from provas.modelos import PhotoInfo
    from provas.motor import PreviewResult
    from provas.ui import MainWindow

    first = str(image_factory("01-first.jpg", color=(190, 40, 40), size=(900, 600)))
    automatic = str(image_factory("02-auto.jpg", color=(40, 90, 190), size=(900, 600)))
    photos = (
        PhotoInfo(first, first, "first", 900, 600, 0, quality=1.0),
        PhotoInfo(automatic, automatic, "auto", 900, 600, 1, quality=0.1),
    )
    target = (1473, 904)

    def face_safe(photo, crop, _target):
        return photo.id == (automatic if crop.zoom < 2 else first)

    monkeypatch.setattr(capas, "_classic_face_safe", face_safe)
    assert capas.selecionar_foto_classica(
        photos, "", ClassicCrop(zoom=1), target
    ) == automatic
    assert capas.selecionar_foto_classica(
        photos, "", ClassicCrop(zoom=2.5), target
    ) == first
    monkeypatch.setattr("provas.ui.crop_dialog.enquadramento.detect_faces", lambda _image: ())

    plan = BookPlan(
        7,
        "prova",
        (first,),
        (
            PagePlan(1, "solo-landscape", (first,), "opening"),
            PagePlan(2, "solo-landscape", (automatic,), "ending"),
        ),
    )
    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan, photos=photos)
    preview = PreviewResult(
        tuple(Image.new("RGB", (420, 297)) for _ in range(3)),
        classic_photo_id=automatic,
        classic_photo_target=target,
    )
    window.apply_preview_ready(preview)

    assert window.project_state.config.foto_capa_id == ""
    window.open_crop_dialog()
    qapp.processEvents()
    dialog = window._crop_dialog
    assert dialog is not None
    assert dialog.photo_path == automatic
    assert dialog.canvas.target_size == target
    dialog.reject()
    qapp.processEvents()
    assert window.project_state.config.foto_capa_id == ""

    preview_requests: list[bool] = []
    monkeypatch.setattr(window, "request_preview", lambda: preview_requests.append(True))
    window.open_crop_dialog()
    qapp.processEvents()
    dialog = window._crop_dialog
    assert dialog is not None
    dialog.zoom_slider.setValue(250)
    dialog.apply_button.click()

    assert window.project_state.config.foto_capa_id == automatic
    assert window.project_state.config.capa_zoom == 2.5
    assert window.project_state.config.capa_enquadramento == "manual"
    assert preview_requests == [True]


def test_crop_without_successful_preview_requests_one_instead_of_guessing(
    qapp, tmp_path: Path, plan, monkeypatch
):
    from provas.ui import MainWindow

    window = MainWindow()
    window.select_folder(str(tmp_path))
    window.apply_analysis_result(plan)
    preview_requests: list[bool] = []
    monkeypatch.setattr(window, "request_preview", lambda: preview_requests.append(True))

    window.open_crop_dialog()

    assert not window.sidebar.crop_button.isEnabled()
    assert window._crop_dialog is None
    assert preview_requests == [True]


def test_close_requests_cancellation_without_waiting_for_worker(qapp):
    from provas.ui import MainWindow

    window = MainWindow()
    cancel_event = threading.Event()
    window.begin_operation("Exportando PDF", cancel_event)

    started = time.perf_counter()
    window.request_shutdown()

    assert cancel_event.is_set()
    assert time.perf_counter() - started < 0.1


def test_close_waits_asynchronously_for_active_qthreads(qapp, tmp_path: Path):
    from provas import motor
    from provas.ui import AnalysisWorker, MainWindow

    window = MainWindow()
    window.show()
    cancel_event = threading.Event()

    def cooperative_operation(config, progresso, cancelar):
        while not cancelar.is_set():
            time.sleep(0.002)
        time.sleep(0.02)
        raise motor.Cancelado()

    window.begin_operation("Analisando fotografias…", cancel_event)
    window._start_worker(
        AnalysisWorker(Config(str(tmp_path)), cancel_event, operation=cooperative_operation),
        lambda _result: None,
    )
    for _ in range(3):
        qapp.processEvents()

    started = time.perf_counter()
    window.close()

    assert cancel_event.is_set()
    assert window.isVisible()
    assert time.perf_counter() - started < 0.1

    deadline = time.perf_counter() + 2
    while window.isVisible() and time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert not window.isVisible()
    assert not window._threads
