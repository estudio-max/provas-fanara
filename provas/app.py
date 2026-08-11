"""Application entry point for the PySide6 editorial editing desk."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .recursos import PRODUCT_NAME
from .ui import MainWindow


def principal() -> int:
    """Start the native application, reusing an existing Qt application in tests."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance()
    owns_application = app is None
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName(PRODUCT_NAME)
    app.setOrganizationName("Provas")
    window = MainWindow()
    window.show()
    if owns_application:
        return app.exec()
    return 0
