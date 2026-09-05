"""Passo a passo que conduz o trabalho, da pasta ao PDF.

Ensina a ordem das escolhas. Repetir na tela um botão que a barra lateral também
tem é proposital: quem está começando não sabe a sequência, e é ela que o passo a
passo mostra. O que ele não faz é reimplementar nada — cada ação chama a mesma
função pública da mesa de edição, e `MainWindow.estado_mudou` diz quando a etapa
terminou.

Por isso o diálogo não é modal: a janela fica visível atrás, preenchendo conforme
o trabalho anda. Fechar a qualquer momento deixa o projeto como está.
"""
from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import recursos


@dataclass(frozen=True)
class Etapa:
    """Uma etapa: o que explica, o que faz e como se sabe que terminou."""

    titulo: str
    descricao: str
    #: Rótulo → nome da ação. Mais de um quando a etapa é uma escolha.
    acoes: tuple[tuple[str, str], ...]
    #: Recebe a janela e devolve se a etapa já está cumprida.
    concluida: Callable[[object], bool]
    #: Etapa de escolha: sempre dá para avançar, mesmo sem tocar em nada.
    opcional: bool = False
    nota: str = ""
    #: Devolve os nomes das ações que estão valendo agora, para marcá-las.
    escolha_atual: Callable[[object], frozenset[str]] | None = None
    #: Imagem mostrada ao abrir a etapa.
    ilustracao: str = ""
    #: Imagem por ação, para o exemplo acompanhar a opção apontada.
    imagens: Mapping[str, str] = field(default_factory=dict)
    #: Rótulo → nome do campo na barra lateral. Editar aqui edita lá.
    campos: tuple[tuple[str, str], ...] = ()


def _tem_pasta(janela) -> bool:
    return bool(getattr(janela, "folder_path", ""))


def _tem_previa(janela) -> bool:
    return getattr(janela, "project_state", None) is not None and bool(
        getattr(janela, "previews", ())
    )


def _exportou(janela) -> bool:
    return bool(getattr(janela, "last_export_path", ""))


def _modo_atual(janela) -> frozenset[str]:
    if not _tem_previa(janela):
        return frozenset()
    prova = getattr(janela, "mode", "") == "prova"
    return frozenset({"analisar_prova" if prova else "analisar_fotolivro"})


def _capa_atual(janela) -> frozenset[str]:
    estado = getattr(janela, "project_state", None)
    if estado is None:
        return frozenset()
    nome = {
        "classica": "capa_classica",
        "mosaico": "capa_mosaico",
        "curvas_editoriais": "capa_curvas",
    }.get(estado.config.estilo_capa, "")
    return frozenset({nome}) if nome else frozenset()


def _acabamento_atual(janela) -> frozenset[str]:
    estado = getattr(janela, "project_state", None)
    if estado is None:
        return frozenset()
    ativos = {f"fundo_{estado.config.fundo_paginas}"}
    if estado.config.sombra_fotos:
        ativos.add("sombra")
    return frozenset(ativos)


def _trocar_fundo(janela, fundo: str) -> None:
    estado = janela.project_state
    janela.set_page_appearance(fundo, estado.config.sombra_fotos if estado else False)


def _alternar_sombra(janela) -> None:
    estado = janela.project_state
    if estado is None:
        return
    janela.set_page_appearance(estado.config.fundo_paginas, not estado.config.sombra_fotos)


_MODOS = (
    "O mesmo ensaio, dois destinos, e a escolha muda o que sai impresso.\n\n"
    "Prova para seleção vai para o cliente escolher as fotos. Cada imagem recebe a "
    "marca d'água — gravada nos pixels, não desenhada por cima — e o código do "
    "arquivo aparece sob a foto, para o cliente anotar o que quer.\n\n"
    "Fotolivro limpo é a entrega final: mesma diagramação, sem marca e sem código, "
    "pronto para a gráfica ou para o cliente guardar."
)


_ACABAMENTO = """O fundo muda o quanto as fotografias saltam. Branco é neutro e imprime barato. Cinza dá descanso ao olho em ensaios claros. Preto adensa as cores e favorece fotos de estúdio, mas gasta muito mais tinta.

A sombra suave descola a fotografia do papel, como se ela estivesse pousada sobre a página."""


ETAPAS: tuple[Etapa, ...] = (
    Etapa(
        "Escolher a pasta do ensaio",
        "Aponte a pasta com as fotografias. JPG ou RAW — para RAW o aplicativo lê a "
        "prévia que a própria câmera gravou dentro do arquivo, sem revelar nada.",
        (("Escolher pasta", "escolher_pasta"), ("Escolher logotipo", "escolher_logotipo")),
        _tem_pasta,
        nota="Preencha a identidade agora: ela assina todas as capas, e aqui ainda não "
             "há prévia para refazer a cada letra digitada.",
        ilustracao="pasta",
        campos=(("Título", "title_edit"),
                ("Fotógrafo / estúdio", "studio_edit"),
                ("Site", "site_edit")),
    ),
    Etapa(
        "Para que serve este PDF?",
        _MODOS,
        (("Analisar como prova", "analisar_prova"),
         ("Analisar como fotolivro", "analisar_fotolivro")),
        _tem_previa,
        nota="Escolher antes de analisar poupa uma volta inteira: o motor já monta as "
             "páginas no modo certo. Dá para trocar depois pela barra lateral.",
        escolha_atual=_modo_atual,
        ilustracao="prova",
        imagens={"analisar_prova": "prova", "analisar_fotolivro": "fotolivro"},
    ),
    Etapa(
        "Acabamento das páginas",
        _ACABAMENTO,
        (("Fundo branco", "fundo_branco"),
         ("Cinza", "fundo_cinza"),
         ("Preto", "fundo_preto"),
         ("Sombra nas fotos", "sombra")),
        _tem_previa,
        opcional=True,
        nota="A sombra é desenhada em cada página do PDF; a prévia mostra exatamente "
             "o que sai impresso.",
        escolha_atual=_acabamento_atual,
        ilustracao="fundo-branco",
        imagens={"fundo_branco": "fundo-branco", "fundo_cinza": "fundo-cinza",
                 "fundo_preto": "fundo-preto", "sombra": "sombra"},
    ),
    Etapa(
        "Estilo da capa",
        "Clássica usa uma fotografia com título e estúdio. Mosaico compõe a grade com "
        "o ensaio inteiro. Curvas editoriais organiza as fotos em formas orgânicas ao "
        "redor do título.",
        (("Clássica", "capa_classica"),
         ("Mosaico", "capa_mosaico"),
         ("Curvas editoriais", "capa_curvas")),
        _tem_previa,
        opcional=True,
        nota="Trocar a capa refaz a prévia e leva alguns segundos. As páginas não são "
             "redesenhadas, só a capa.",
        escolha_atual=_capa_atual,
        ilustracao="capa-classica",
        imagens={"capa_classica": "capa-classica", "capa_mosaico": "capa-mosaico",
                 "capa_curvas": "capa-curvas"},
    ),
    Etapa(
        "Exportar o PDF",
        "Revise a prévia atrás desta janela, troque a diagramação de qualquer página "
        "pelo botão de ciclo dela, e exporte quando estiver bom. Ou salve o projeto "
        "para continuar depois.",
        (("Exportar PDF", "exportar"),),
        _exportou,
        nota="O projeto salvo guarda a diagramação e o caminho das fotos, nunca as imagens.",
        ilustracao="exportar",
    ),
)


def _analisar(janela, modo: str) -> None:
    """Fixa o modo antes de analisar.

    O modo entra no rascunho e a análise já monta as páginas com marca e código,
    ou sem — em vez de renderizar tudo e refazer na escolha seguinte.
    """
    janela.set_mode(modo)
    janela.request_analysis()


#: Nome da ação → o que fazer com a janela. Nada aqui reimplementa lógica.
ACOES: dict[str, Callable[[object], None]] = {
    "escolher_pasta": lambda janela: janela.choose_folder(),
    "escolher_logotipo": lambda janela: janela.sidebar.logo_choose_button.click(),
    "analisar_prova": lambda janela: _analisar(janela, "prova"),
    "analisar_fotolivro": lambda janela: _analisar(janela, "fotolivro"),
    "fundo_branco": lambda janela: _trocar_fundo(janela, "branco"),
    "fundo_cinza": lambda janela: _trocar_fundo(janela, "cinza"),
    "fundo_preto": lambda janela: _trocar_fundo(janela, "preto"),
    "sombra": _alternar_sombra,
    "capa_classica": lambda janela: janela.set_cover_style("classica"),
    "capa_mosaico": lambda janela: janela.set_cover_style("mosaico"),
    "capa_curvas": lambda janela: janela.set_cover_style("curvas_editoriais"),
    "exportar": lambda janela: janela.export_dialog(),
}


class WizardDialog(QDialog):
    """Conduz o fluxo operando a própria mesa de edição."""

    def __init__(self, janela, parent: QWidget | None = None) -> None:
        super().__init__(parent or janela)
        self.janela = janela
        self.setObjectName("wizardDialog")
        self.setWindowTitle(f"Primeiros passos · {recursos.PRODUCT_NAME}")
        # Não modal: a mesa de edição precisa continuar visível e utilizável atrás.
        self.setModal(False)
        # Um mínimo fixo abaixo do que o conteúdo pede faz os widgets se
        # sobreporem — foi o que aconteceu quando a primeira etapa ganhou os
        # campos de identidade. O piso vem do próprio layout; aqui só o tamanho
        # confortável de abertura.
        self.resize(1040, 700)
        # Recebe o foco quando os botões desabilitam, para o anel não descer
        # sozinho até a caixa de seleção.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._indice = 0
        self._botoes_acao: list[QPushButton] = []
        self._acao_do_botao: dict[QPushButton, str] = {}
        self._estava_ocupada = False
        self._pixmaps: dict[str, QPixmap] = {}
        self._ilustracao_fixada = ""

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._painel_exemplo())

        coluna = QWidget()
        coluna.setObjectName("wizardColumn")
        conteudo = QVBoxLayout(coluna)
        conteudo.setContentsMargins(28, 24, 28, 20)
        conteudo.setSpacing(0)
        raiz.addWidget(coluna, 1)

        conteudo.addLayout(self._cabecalho())
        conteudo.addSpacing(18)

        self.titulo = QLabel()
        self.titulo.setObjectName("wizardStepTitle")
        self.titulo.setWordWrap(True)
        conteudo.addWidget(self.titulo)
        conteudo.addSpacing(8)

        self.descricao = QLabel()
        self.descricao.setObjectName("mutedText")
        self.descricao.setWordWrap(True)
        conteudo.addWidget(self.descricao)

        self.nota = QLabel()
        self.nota.setObjectName("wizardNote")
        self.nota.setWordWrap(True)
        conteudo.addSpacing(12)
        conteudo.addWidget(self.nota)

        self.campos = QFormLayout()
        self.campos.setContentsMargins(0, 14, 0, 0)
        self.campos.setSpacing(8)
        self.campos.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.campos.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Rótulo acima do campo, como na barra lateral: ao lado, "Fotógrafo /
        # estúdio" disputa a largura com o próprio campo nesta coluna estreita.
        self.campos.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        conteudo.addLayout(self.campos)

        conteudo.addStretch(1)
        conteudo.addSpacing(14)
        self.acoes = QHBoxLayout()
        self.acoes.setContentsMargins(0, 0, 0, 0)
        self.acoes.setSpacing(8)
        conteudo.addLayout(self.acoes)

        self.aguarde = QLabel()
        self.aguarde.setObjectName("wizardBusy")
        self.aguarde.setWordWrap(True)
        conteudo.addWidget(self.aguarde)

        conteudo.addSpacing(18)
        self.nao_mostrar = QCheckBox("Não mostrar este passo a passo ao abrir")
        conteudo.addWidget(self.nao_mostrar)

        conteudo.addSpacing(14)
        conteudo.addLayout(self._navegacao())
        conteudo.addSpacing(16)
        conteudo.addWidget(self._rodape())

        janela.estado_mudou.connect(self._estado_mudou)
        self._mostrar_etapa()

    # ---------- partes fixas ----------

    def _painel_exemplo(self) -> QWidget:
        """Coluna da esquerda: o exemplo do que a etapa está falando."""
        painel = QFrame()
        painel.setObjectName("wizardExample")
        painel.setFixedWidth(400)
        caixa = QVBoxLayout(painel)
        caixa.setContentsMargins(0, 0, 0, 0)
        caixa.setSpacing(0)

        self.exemplo = QLabel()
        self.exemplo.setObjectName("wizardExampleImage")
        self.exemplo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.exemplo.setScaledContents(False)
        caixa.addWidget(self.exemplo, 1)
        return painel

    def _mostrar_ilustracao(self, nome: str) -> None:
        """Carrega a imagem da etapa, ou da opção apontada."""
        if not nome:
            self.exemplo.clear()
            return
        pixmap = self._pixmaps.get(nome)
        if pixmap is None:
            caminho = recursos.caminho(f"passo-a-passo/{nome}.jpg")
            pixmap = QPixmap(str(caminho))
            self._pixmaps[nome] = pixmap
        if pixmap.isNull():
            self.exemplo.clear()
            return
        # Segue o tamanho real do painel: fixar 368x300 desperdiçava metade da
        # altura disponível. Uma imagem em 2:3 preenche a coluna inteira.
        area = self.exemplo.size()
        self.exemplo.setPixmap(pixmap.scaled(
            area.width(), area.height(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))


    def _cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(14)

        marca = QLabel()
        marca.setObjectName("brandMark")
        marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marca.setStyleSheet("background: transparent;")
        marca.setPixmap(QPixmap(str(recursos.caminho("fanara-symbol.png"))).scaled(
            32, 32, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        linha.addWidget(marca, 0, Qt.AlignmentFlag.AlignVCenter)

        nome = QLabel(recursos.PRODUCT_NAME)
        nome.setObjectName("welcomeTitle")
        linha.addWidget(nome)
        linha.addStretch(1)

        self.contador = QLabel()
        self.contador.setObjectName("wizardCounter")
        linha.addWidget(self.contador, 0, Qt.AlignmentFlag.AlignVCenter)
        return linha

    def _navegacao(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(10)

        self.fechar = QPushButton("Fechar")
        self.fechar.setToolTip("Fecha o passo a passo e mantém tudo o que já foi feito")
        self.fechar.clicked.connect(self.reject)
        linha.addWidget(self.fechar)
        linha.addStretch(1)

        self.voltar = QPushButton("Voltar")
        self.voltar.clicked.connect(self._voltar)
        linha.addWidget(self.voltar)

        self.avancar = QPushButton("Avançar")
        self.avancar.setObjectName("importantButton")
        self.avancar.clicked.connect(self._avancar)
        linha.addWidget(self.avancar)
        return linha

    def _rodape(self) -> QWidget:
        rodape = QFrame()
        rodape.setObjectName("welcomeFooter")
        linha = QHBoxLayout(rodape)
        linha.setContentsMargins(0, 12, 0, 0)
        linha.setSpacing(12)
        build = QLabel(recursos.identificacao_da_build())
        build.setObjectName("welcomeFinePrint")
        direitos = QLabel(recursos.COPYRIGHT)
        direitos.setObjectName("welcomeFinePrint")
        linha.addWidget(build)
        linha.addStretch(1)
        linha.addWidget(direitos)
        return rodape

    # ---------- etapa corrente ----------

    @property
    def etapa(self) -> Etapa:
        return ETAPAS[self._indice]

    def _mostrar_etapa(self) -> None:
        etapa = self.etapa
        self.contador.setText(f"Passo {self._indice + 1} de {len(ETAPAS)}")
        self.titulo.setText(etapa.titulo)
        self.descricao.setText(etapa.descricao)
        self.nota.setText(etapa.nota)
        self.nota.setVisible(bool(etapa.nota))

        while self.campos.count():
            item = self.campos.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for rotulo, atributo in etapa.campos:
            espelho = getattr(self.janela.sidebar, atributo, None)
            if espelho is None:
                continue
            campo = QLineEdit(espelho.text())
            campo.setAccessibleName(espelho.accessibleName() or rotulo)
            campo.setPlaceholderText(espelho.placeholderText())
            # A barra lateral continua sendo a fonte da verdade: escrever aqui
            # escreve lá, e o caminho de sinal que já existe faz o resto.
            campo.textEdited.connect(
                lambda texto, alvo=espelho: alvo.setText(texto)
            )
            self.campos.addRow(rotulo, campo)

        while self.acoes.count():
            item = self.acoes.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # `deleteLater` só destrói no próximo ciclo do laço, e até lá o
                # botão continua filho do diálogo, pintando por cima dos novos.
                widget.setParent(None)
                widget.deleteLater()
        self._botoes_acao.clear()
        self._acao_do_botao.clear()

        for rotulo, acao in etapa.acoes:
            botao = QPushButton(rotulo)
            botao.setObjectName("wizardAction")
            botao.clicked.connect(lambda _c=False, nome=acao: self._executar(nome))
            # Apontar um botão troca o exemplo, sem precisar clicar.
            botao.installEventFilter(self)
            self.acoes.addWidget(botao)
            self._botoes_acao.append(botao)
            self._acao_do_botao[botao] = acao
        self.acoes.addStretch(1)

        self.voltar.setEnabled(self._indice > 0)
        self._ilustracao_fixada = ""
        self._sincronizar()
        self._focar_acao()

    def _focar_acao(self) -> None:
        """Põe o foco na ação da etapa.

        Sem isto o foco cai na caixa de seleção e o anel do tema disputa atenção
        com o que importa. Precisa acontecer a cada troca de etapa e também no
        `showEvent`: um `setFocus` antes de a janela existir na tela é descartado.
        """
        if not (self._botoes_acao and self._botoes_acao[0].isEnabled()):
            return
        # Depois das remoções pendentes: destruir o botão que tinha foco faz o Qt
        # reatribuí-lo, e isso acontece no ciclo seguinte, por cima de um
        # `setFocus` feito agora.
        botao = self._botoes_acao[0]
        QTimer.singleShot(0, botao, botao.setFocus)

    def _sincronizar(self) -> None:
        """Habilita, marca e informa, conforme o estado atual do projeto."""
        ocupada = bool(getattr(self.janela, "is_busy", False))
        etapa = self.etapa
        escolhidas = etapa.escolha_atual(self.janela) if etapa.escolha_atual else frozenset()

        for botao in self._botoes_acao:
            botao.setEnabled(not ocupada)
            # Marca a opção que está valendo: sem isto o clique não deixa rastro
            # e não dá para saber qual modo ou capa está ativo.
            ativo = self._acao_do_botao.get(botao) in escolhidas
            if botao.property("ativo") != ativo:
                botao.setProperty("ativo", ativo)
                botao.style().unpolish(botao)
                botao.style().polish(botao)

        # O que a janela está fazendo, dito aqui: a barra de status fica no alto,
        # longe de onde o olho está, e o silêncio parecia travamento.
        etapa_imagens = etapa.imagens
        preferida = next((etapa_imagens[nome] for nome in escolhidas if nome in etapa_imagens), "")
        self._mostrar_ilustracao(self._ilustracao_fixada or preferida or etapa.ilustracao)

        self.aguarde.setText(str(getattr(self.janela, "status_message", "")) if ocupada else "")
        self.aguarde.setVisible(ocupada)

        pronta = etapa.opcional or etapa.concluida(self.janela)
        ultima = self._indice == len(ETAPAS) - 1
        self.avancar.setText("Concluir" if ultima else "Avançar")
        self.avancar.setEnabled((pronta or ultima) and not ocupada)

        if ocupada and not self._estava_ocupada:
            # Segura o foco no próprio diálogo enquanto tudo está desabilitado,
            # senão o Qt o empurra para a caixa de seleção.
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        elif self._estava_ocupada and not ocupada:
            self._focar_acao()
        self._estava_ocupada = ocupada

    def _estado_mudou(self) -> None:
        anterior = self.etapa
        self._sincronizar()
        # Etapa de ação cumprida: segue sozinho, para o passo a passo acompanhar
        # o trabalho em vez de esperar um clique redundante.
        if (
            not anterior.opcional
            and self._indice < len(ETAPAS) - 1
            and anterior.concluida(self.janela)
            and not getattr(self.janela, "is_busy", False)
        ):
            self._indice += 1
            self._mostrar_etapa()

    # ---------- ações ----------

    def _executar(self, nome: str) -> None:
        try:
            acao = ACOES[nome]
        except KeyError:
            raise ValueError(f"Ação desconhecida no passo a passo: {nome!r}") from None
        acao(self.janela)
        self._sincronizar()

    def _avancar(self) -> None:
        if self._indice >= len(ETAPAS) - 1:
            self.accept()
            return
        self._indice += 1
        self._mostrar_etapa()

    def _voltar(self) -> None:
        if self._indice > 0:
            self._indice -= 1
            self._mostrar_etapa()

    def eventFilter(self, objeto, evento) -> bool:
        if isinstance(objeto, QPushButton) and objeto in self._acao_do_botao:
            if evento.type() == QEvent.Type.Enter:
                self._ilustracao_fixada = self.etapa.imagens.get(
                    self._acao_do_botao[objeto], "")
                self._sincronizar()
            elif evento.type() == QEvent.Type.Leave:
                self._ilustracao_fixada = ""
                self._sincronizar()
        return super().eventFilter(objeto, evento)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._focar_acao()
        self._sincronizar()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sincronizar()

    @property
    def dispensado(self) -> bool:
        """Se o usuário pediu para não ver o passo a passo de novo."""
        return self.nao_mostrar.isChecked()
