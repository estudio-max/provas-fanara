"""Tela de abertura com os três passos do primeiro uso.

Explica o caminho da pasta ao PDF e oferece o primeiro passo como ação. Não
refaz o fluxo dentro do modal: a mesa de edição continua sendo o único lugar
onde o trabalho acontece.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import recursos

PASSOS = (
    ("Escolher pasta",
     "Aponte a pasta do ensaio. JPG ou RAW — o aplicativo lê a prévia que a "
     "própria câmera gravou dentro do arquivo."),
    ("Analisar fotografias",
     "O motor avalia nitidez, exposição e semelhança entre as fotos e propõe a "
     "diagramação inteira, com uma prévia editável."),
    ("Exportar PDF",
     "Revise a prévia, troque o que quiser e exporte. Ou salve o projeto para "
     "continuar depois, sem perder nada."),
)


class WelcomeDialog(QDialog):
    """Abertura do aplicativo. `Accepted` significa “quero escolher a pasta agora”."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("welcomeDialog")
        self.setWindowTitle(f"Bem-vindo ao {recursos.PRODUCT_NAME}")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(0)

        layout.addLayout(self._cabecalho())
        layout.addSpacing(26)

        for numero, (titulo, descricao) in enumerate(PASSOS, start=1):
            layout.addWidget(self._passo(numero, titulo, descricao))
            if numero < len(PASSOS):
                layout.addSpacing(18)

        layout.addSpacing(28)
        self.nao_mostrar = QCheckBox("Não mostrar novamente ao abrir")
        layout.addWidget(self.nao_mostrar)

        layout.addSpacing(20)
        layout.addLayout(self._acoes())
        layout.addSpacing(22)
        layout.addWidget(self._rodape())

    # ---------- partes ----------

    def _cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(14)

        marca = QLabel()
        marca.setObjectName("brandMark")
        marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marca.setStyleSheet("background: transparent;")
        marca.setPixmap(QPixmap(str(recursos.caminho("fanara-symbol.png"))).scaled(
            36, 36, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        linha.addWidget(marca, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setContentsMargins(0, 0, 0, 0)
        textos.setSpacing(4)
        titulo = QLabel(recursos.PRODUCT_NAME)
        titulo.setObjectName("welcomeTitle")
        resumo = QLabel("Da pasta do ensaio ao fotolivro pronto, em três passos.")
        resumo.setObjectName("mutedText")
        resumo.setWordWrap(True)
        textos.addWidget(titulo)
        textos.addWidget(resumo)
        linha.addLayout(textos, 1)
        return linha

    def _passo(self, numero: int, titulo: str, descricao: str) -> QWidget:
        passo = QWidget()
        linha = QHBoxLayout(passo)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(14)

        indice = QLabel(str(numero))
        indice.setObjectName("welcomeStepNumber")
        indice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(indice, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setContentsMargins(0, 0, 0, 0)
        textos.setSpacing(3)
        nome = QLabel(titulo)
        nome.setObjectName("sectionTitle")
        detalhe = QLabel(descricao)
        detalhe.setObjectName("mutedText")
        detalhe.setWordWrap(True)
        textos.addWidget(nome)
        textos.addWidget(detalhe)
        linha.addLayout(textos, 1)
        return passo

    def _acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(10)
        linha.addStretch(1)

        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.reject)
        linha.addWidget(fechar)

        escolher = QPushButton("Escolher pasta")
        escolher.setObjectName("importantButton")
        escolher.setDefault(True)
        escolher.clicked.connect(self.accept)
        linha.addWidget(escolher)
        # Sem isto o foco inicial cai na caixa de seleção, e o anel de foco do
        # tema disputa atenção com a ação principal.
        self._acao_principal = escolher
        return linha

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._acao_principal.setFocus()

    def _rodape(self) -> QWidget:
        rodape = QFrame()
        rodape.setObjectName("welcomeFooter")
        linha = QHBoxLayout(rodape)
        linha.setContentsMargins(0, 14, 0, 0)
        linha.setSpacing(12)

        build = QLabel(recursos.identificacao_da_build())
        build.setObjectName("welcomeFinePrint")
        direitos = QLabel(recursos.COPYRIGHT)
        direitos.setObjectName("welcomeFinePrint")
        linha.addWidget(build)
        linha.addStretch(1)
        linha.addWidget(direitos)
        return rodape

    # ---------- resultado ----------

    @property
    def dispensada(self) -> bool:
        """Se o usuário pediu para não ver esta tela de novo."""
        return self.nao_mostrar.isChecked()
