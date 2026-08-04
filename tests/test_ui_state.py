from __future__ import annotations

import os
import threading
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from provas.modelos import BookPlan, PagePlan
from provas.motor import Config, Resultado


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


def test_close_requests_cancellation_without_waiting_for_worker(qapp):
    from provas.ui import MainWindow

    window = MainWindow()
    cancel_event = threading.Event()
    window.begin_operation("Exportando PDF", cancel_event)

    started = time.perf_counter()
    window.request_shutdown()

    assert cancel_event.is_set()
    assert time.perf_counter() - started < 0.1
