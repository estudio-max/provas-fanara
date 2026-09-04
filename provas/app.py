"""Application entry point for the PySide6 editorial editing desk."""
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from . import preferencias
from .recursos import ORGANIZATION_NAME, PRODUCT_NAME, VERSION
from .ui import MainWindow, WelcomeDialog


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
    app.setApplicationVersion(VERSION)
    app.setOrganizationName(ORGANIZATION_NAME)
    window = MainWindow()
    window.show()
    # Depois do primeiro ciclo do laço: a mesa de edição pinta primeiro e a
    # abertura surge sobre ela, em vez de a janela nascer atrás de um modal.
    QTimer.singleShot(0, app, lambda: abrir_boas_vindas(window))
    if owns_application:
        return app.exec()
    return 0


def abrir_boas_vindas(window: MainWindow) -> None:
    """Mostra a abertura sobre a janela já visível, se o usuário não a dispensou."""
    if not preferencias.mostrar_boas_vindas():
        return
    dialogo = WelcomeDialog(window)
    escolher_pasta = dialogo.exec() == int(WelcomeDialog.DialogCode.Accepted)
    if dialogo.dispensada:
        preferencias.definir_mostrar_boas_vindas(False)
    if escolher_pasta:
        window.choose_folder()
