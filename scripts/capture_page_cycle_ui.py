"""Capture the page-layout controls in their required visual QA states."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "1.25")

from PIL import Image
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from provas.modelos import BookPlan, PagePlan
from provas.ui import MainWindow


ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "tmp" / "ui-qa"


def _plan() -> BookPlan:
    pages = tuple(
        PagePlan(
            number,
            "solo-landscape",
            (f"page-{number}.jpg",),
            "opening" if number == 1 else "ending" if number == 6 else "narrative",
        )
        for number in range(1, 7)
    )
    return BookPlan(71, "prova", ("cover.jpg",), pages)


def _capture(window: MainWindow, name: str) -> Path:
    for _ in range(4):
        QApplication.processEvents()
    path = OUTPUT / name
    window.grab().save(str(path))
    return path


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    for font_name in (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/segoeuil.ttf",
        "C:/Windows/Fonts/seguisym.ttf",
    ):
        QFontDatabase.addApplicationFont(font_name)
    app.setStyleSheet((ROOT / "provas" / "ui" / "theme.qss").read_text(encoding="utf-8"))

    window = MainWindow()
    window.resize(1093, 614)
    window.show()
    plan = _plan()
    window.select_folder(str(OUTPUT))
    window.apply_analysis_result(plan)
    previews = (
        Image.new("RGB", (420, 297), "#2E3946"),
        Image.new("RGB", (420, 297), "#D4E6F1"),
        Image.new("RGB", (420, 297), "#E8D8C9"),
        Image.new("RGB", (420, 297), "#CFE0D3"),
        Image.new("RGB", (420, 297), "#E5D4E8"),
        Image.new("RGB", (420, 297), "#EAE3C7"),
        Image.new("RGB", (420, 297), "#D3D8E9"),
    )
    window.apply_preview_ready(previews)
    grid = window.preview_grid
    grid.set_page_alternatives({1, 3, 5})
    normal = _capture(window, "page-cycle-normal-1093x614.png")
    grid.set_page_busy(1, True)
    busy = _capture(window, "page-cycle-busy-1093x614.png")
    grid.set_page_busy(1, False)
    grid.set_page_alternatives(set())
    unavailable = _capture(window, "page-cycle-no-alternative-1093x614.png")
    window.close()
    print(f"{normal}\n{busy}\n{unavailable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
