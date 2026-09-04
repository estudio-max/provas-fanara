from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QWidget

from provas import app as aplicacao
from provas import recursos
from provas.ui import WelcomeDialog
from provas.ui.welcome_dialog import PASSOS


@pytest.fixture
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _textos(dialogo: WelcomeDialog) -> list[str]:
    return [rotulo.text() for rotulo in dialogo.findChildren(QLabel)]


def test_abertura_mostra_os_tres_passos_e_a_build(qt_app: QApplication) -> None:
    dialogo = WelcomeDialog()
    textos = _textos(dialogo)

    for numero, (titulo, descricao) in enumerate(PASSOS, start=1):
        assert titulo in textos
        assert descricao in textos
        assert str(numero) in textos

    assert recursos.identificacao_da_build() in textos
    assert recursos.COPYRIGHT in textos
    assert recursos.VERSION in recursos.identificacao_da_build()
    assert not dialogo.dispensada
    dialogo.deleteLater()


def test_marcar_nao_mostrar_grava_a_preferencia(qt_app: QApplication, monkeypatch) -> None:
    """A janela só grava a escolha depois de fechada, e só quando marcada."""
    gravado: list[bool] = []
    monkeypatch.setattr(aplicacao.preferencias, "mostrar_boas_vindas", lambda: True)
    monkeypatch.setattr(aplicacao.preferencias, "definir_mostrar_boas_vindas",
                        lambda mostrar: gravado.append(mostrar))

    pastas: list[str] = []

    class JanelaFalsa(QWidget):
        """A abertura é filha da janela, então precisa mesmo ser um QWidget."""

        def choose_folder(self) -> None:
            pastas.append("escolhida")

    def responder(marcar: bool, aceitar: bool):
        def exec_falso(self) -> int:
            self.findChild(QCheckBox).setChecked(marcar)
            return int(WelcomeDialog.DialogCode.Accepted if aceitar
                       else WelcomeDialog.DialogCode.Rejected)
        return exec_falso

    monkeypatch.setattr(WelcomeDialog, "exec", responder(marcar=True, aceitar=True))
    aplicacao.abrir_boas_vindas(JanelaFalsa())
    assert gravado == [False], "marcar 'não mostrar novamente' desliga a abertura"
    assert pastas == ["escolhida"], "'Escolher pasta' abre o seletor de pasta"

    gravado.clear()
    pastas.clear()
    monkeypatch.setattr(WelcomeDialog, "exec", responder(marcar=False, aceitar=False))
    aplicacao.abrir_boas_vindas(JanelaFalsa())
    assert gravado == [], "fechar sem marcar não altera a preferência"
    assert pastas == [], "fechar não abre o seletor de pasta"


def test_preferencia_desligada_nao_abre_a_janela(qt_app: QApplication, monkeypatch) -> None:
    monkeypatch.setattr(aplicacao.preferencias, "mostrar_boas_vindas", lambda: False)

    def nunca(self) -> int:
        raise AssertionError("a abertura não deveria ser construída")

    monkeypatch.setattr(WelcomeDialog, "exec", nunca)
    aplicacao.abrir_boas_vindas(object())
