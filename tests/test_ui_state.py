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
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QLineEdit

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
            PagePlan(1, "solo-landscape", (photos[0],), "opening"),
            PagePlan(2, "triptych-balanced", photos[1:], "ending"),
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


def test_sidebar_exposes_two_cover_styles_and_accessible_identity_fields(qapp):
    from provas.ui.sidebar import WorkflowSidebar

    sidebar = WorkflowSidebar()

    assert [sidebar.cover_style.itemData(index) for index in range(sidebar.cover_style.count())] == [
        "mosaico",
        "curvas_editoriais",
    ]
    assert [sidebar.cover_style.itemText(index) for index in range(sidebar.cover_style.count())] == [
        "Mosaico editorial",
        "Curvas editoriais",
    ]
    assert sidebar.title_edit.accessibleName() == "Título da capa"
    assert sidebar.studio_edit.accessibleName() == "Nome do fotógrafo ou estúdio"
    assert sidebar.site_edit.accessibleName() == "Site do fotógrafo ou estúdio"
    assert sidebar.logo_choose_button.accessibleName() == "Escolher logotipo da capa"
    assert sidebar.logo_remove_button.accessibleName() == "Remover logotipo da capa"
    assert all(edit.minimumHeight() >= 36 for edit in sidebar.findChildren(QLineEdit))


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
    deadline = time.perf_counter() + 0.5
    while not identities and time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert identities == [{
        "titulo": "Aurora editorial",
        "estudio": "Fanara",
        "site": "fanara.com.br/ensaios",
        "logo": "marca.png",
    }]


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


def test_preview_translates_generated_sequence_role(qapp, tmp_path: Path, plan):
    from provas.ui.preview_grid import PreviewGrid

    sequence = replace(
        plan,
        pages=(PagePlan(1, "pair-landscapes", plan.pages[1].photo_ids[:2], "sequence"),),
    )
    grid = PreviewGrid()
    grid.set_previews(sequence, (Image.new("RGB", (420, 297)),))

    assert grid.page_roles == ("Sequência",)


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
