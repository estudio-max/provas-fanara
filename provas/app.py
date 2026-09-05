"""Application entry point for the PySide6 editorial editing desk."""
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from . import preferencias
from .recursos import ORGANIZATION_NAME, PRODUCT_NAME, VERSION
from .ui import MainWindow, WizardDialog


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
    # Depois do primeiro ciclo do laço: a mesa de edição pinta primeiro e o
    # passo a passo surge sobre ela, em vez de a janela nascer atrás do diálogo.
    QTimer.singleShot(0, app, lambda: abrir_passo_a_passo(window))
    if owns_application:
        return app.exec()
    return 0


def abrir_passo_a_passo(window: MainWindow) -> None:
    """Abre o passo a passo sobre a janela, se o usuário não o dispensou.

    Não bloqueia: o passo a passo opera a mesa de edição, que precisa continuar
    viva atrás dele. A preferência é gravada quando o diálogo fecha.
    """
    if not preferencias.mostrar_boas_vindas():
        return
    dialogo = WizardDialog(window)
    # Guardado na janela: um diálogo não modal solto seria coletado ao sair daqui.
    window._passo_a_passo = dialogo
    dialogo.finished.connect(
        lambda _resultado: preferencias.definir_mostrar_boas_vindas(False)
        if dialogo.dispensado
        else None
    )
    dialogo.show()
