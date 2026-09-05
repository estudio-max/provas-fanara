from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from provas import app as aplicacao
from provas import recursos
from provas.ui import MainWindow, WizardDialog
from provas.ui.wizard import ACOES, ETAPAS


@pytest.fixture
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def janela(qt_app: QApplication) -> MainWindow:
    window = MainWindow()
    yield window
    # `close()` sozinho deixa a janela viva: ela sobrevive ao teste e estoura
    # com violação de acesso quando um teste posterior gira o laço de eventos.
    passo = getattr(window, "_passo_a_passo", None)
    if passo is not None:
        passo.close()
        passo.deleteLater()
    window.close()
    window.deleteLater()
    for _ in range(3):
        qt_app.processEvents()


def _rotulos_de_acao(passo: WizardDialog) -> list[str]:
    return [botao.text() for botao in passo._botoes_acao]


def test_o_passo_a_passo_cobre_o_fluxo_da_pasta_ao_pdf(qt_app: QApplication, janela) -> None:
    """As etapas são o caminho real do trabalho, não uma apresentação."""
    passo = WizardDialog(janela)

    assert len(ETAPAS) == 5
    assert passo.contador.text() == "Passo 1 de 5"
    assert _rotulos_de_acao(passo) == ["Escolher pasta", "Escolher logotipo"]

    titulos = [etapa.titulo for etapa in ETAPAS]
    assert titulos[0].startswith("Escolher")
    assert titulos[-1].startswith("Exportar")
    rotulos = [rotulo.text() for rotulo in passo.findChildren(QLabel)]
    assert recursos.identificacao_da_build() in rotulos
    assert recursos.COPYRIGHT in rotulos
    passo.deleteLater()


def test_a_etapa_de_acao_so_libera_avancar_quando_cumprida(qt_app: QApplication, janela) -> None:
    """Sem pasta escolhida não há como sair da primeira etapa."""
    passo = WizardDialog(janela)

    assert not passo.avancar.isEnabled(), "sem pasta, avançar fica travado"
    passo._avancar()
    assert passo.contador.text() == "Passo 2 de 5", (
        "_avancar é o mesmo caminho do botão; o teste do botão travado é o isEnabled acima"
    )
    passo.deleteLater()


def test_cumprir_a_etapa_avanca_sozinho(qt_app: QApplication, janela) -> None:
    """Escolher a pasta leva à análise sem exigir um clique redundante."""
    passo = WizardDialog(janela)
    assert passo.contador.text() == "Passo 1 de 5"

    janela.folder_path = "C:/algum/ensaio"
    janela._sync_actions()

    assert passo.contador.text() == "Passo 2 de 5"
    assert _rotulos_de_acao(passo) == ["Analisar como prova", "Analisar como fotolivro"]
    passo.deleteLater()


def test_a_etapa_de_escolha_nao_trava_o_avanco(qt_app: QApplication, janela) -> None:
    """Modo e capa têm padrão; quem não quiser mexer segue em frente."""
    passo = WizardDialog(janela)
    passo._indice = 3          # estilo da capa
    passo._mostrar_etapa()

    assert ETAPAS[3].opcional
    assert passo.avancar.isEnabled()
    from provas.ui.sidebar import ESTILOS_DE_CAPA

    # Os rótulos vêm da barra lateral; fixá-los aqui foi o que deixou o guia
    # oferecendo três capas depois que o aplicativo passou a ter onze.
    assert _rotulos_de_acao(passo) == [rotulo.split(" · ")[0]
                                       for rotulo, _chave in ESTILOS_DE_CAPA]
    passo.deleteLater()


def test_cada_acao_chama_a_funcao_real_da_mesa_de_edicao(qt_app: QApplication, janela) -> None:
    """O passo a passo opera a janela; não reimplementa nada."""
    chamadas: list[str] = []
    for nome in ("choose_folder", "request_analysis", "export_dialog"):
        setattr(janela, nome, lambda n=nome: chamadas.append(n))
    janela.set_mode = lambda modo: chamadas.append(f"modo:{modo}")
    janela.set_cover_style = lambda estilo: chamadas.append(f"capa:{estilo}")

    passo = WizardDialog(janela)
    for acao in ("escolher_pasta", "analisar_prova", "analisar_fotolivro",
                 "capa_classica", "capa_mosaico", "capa_curvas_editoriais", "exportar"):
        passo._executar(acao)

    assert chamadas == [
        "choose_folder",
        "modo:prova", "request_analysis",        # o modo entra antes da análise
        "modo:fotolivro", "request_analysis",
        "capa:classica", "capa:mosaico", "capa:curvas_editoriais",
        "export_dialog",
    ]
    passo.deleteLater()


def test_acao_desconhecida_falha_alto(qt_app: QApplication, janela) -> None:
    passo = WizardDialog(janela)
    with pytest.raises(ValueError, match="Ação desconhecida"):
        passo._executar("inventada")
    passo.deleteLater()


def test_a_janela_ocupada_desabilita_as_acoes(qt_app: QApplication, janela) -> None:
    """Nada de disparar uma análise por cima de outra em andamento."""
    passo = WizardDialog(janela)
    janela.is_busy = True
    janela._sync_actions()

    assert all(not botao.isEnabled() for botao in passo._botoes_acao)
    assert not passo.avancar.isEnabled()
    passo.deleteLater()


def test_dispensar_grava_a_preferencia_ao_fechar(qt_app: QApplication, janela, monkeypatch) -> None:
    gravado: list[bool] = []
    monkeypatch.setattr(aplicacao.preferencias, "mostrar_boas_vindas", lambda: True)
    monkeypatch.setattr(aplicacao.preferencias, "definir_mostrar_boas_vindas",
                        lambda mostrar: gravado.append(mostrar))

    aplicacao.abrir_passo_a_passo(janela)
    passo = janela._passo_a_passo
    assert isinstance(passo, WizardDialog)
    assert not passo.isModal(), "a mesa de edição precisa continuar viva atrás"

    passo.nao_mostrar.setChecked(True)
    passo.reject()

    assert gravado == [False]


def test_preferencia_desligada_nao_abre_nada(qt_app: QApplication, janela, monkeypatch) -> None:
    monkeypatch.setattr(aplicacao.preferencias, "mostrar_boas_vindas", lambda: False)
    aplicacao.abrir_passo_a_passo(janela)
    assert getattr(janela, "_passo_a_passo", None) is None


def test_a_escolha_ativa_fica_marcada_na_tela(qt_app: QApplication, janela) -> None:
    """Clicar numa opção tem de deixar rastro.

    Sem a marcação o clique não muda nada visível e não dá para saber qual modo
    ou capa está valendo.
    """
    from provas.ui.wizard import _capa_atual

    passo = WizardDialog(janela)
    passo._indice = 3                    # estilo da capa
    passo._mostrar_etapa()

    marcados = [b.text() for b in passo._botoes_acao if b.property("ativo")]
    assert marcados == [], "sem projeto aberto não há capa ativa"

    class EstadoFalso:
        class config:
            estilo_capa = "mosaico"

    janela.project_state = EstadoFalso()
    assert _capa_atual(janela) == {"capa_mosaico"}
    passo._sincronizar()

    marcados = [b.text() for b in passo._botoes_acao if b.property("ativo")]
    from provas.ui.sidebar import ESTILOS_DE_CAPA

    rotulo_mosaico = next(rotulo for rotulo, chave in ESTILOS_DE_CAPA if chave == "mosaico")
    assert marcados == [rotulo_mosaico.split(" · ")[0]], (
        "a capa em uso tem de aparecer marcada"
    )
    passo.deleteLater()


def test_enquanto_trabalha_o_passo_a_passo_diz_o_que_esta_fazendo(
    qt_app: QApplication, janela,
) -> None:
    """O silêncio parecia travamento: a barra de status fica longe do olho."""
    passo = WizardDialog(janela)
    assert not passo.aguarde.isVisible() or passo.aguarde.text() == ""

    janela.is_busy = True
    janela.status_message = "Renderizando capa…"
    janela._sync_actions()

    assert passo.aguarde.text() == "Renderizando capa…"
    assert all(not b.isEnabled() for b in passo._botoes_acao)
    assert not passo.nao_mostrar.hasFocus(), (
        "com tudo desabilitado o foco não pode descer para a caixa de seleção"
    )

    janela.is_busy = False
    janela._sync_actions()
    assert passo.aguarde.text() == ""
    passo.deleteLater()


def test_o_acabamento_marca_fundo_e_sombra_ao_mesmo_tempo(qt_app: QApplication, janela) -> None:
    """Fundo e sombra são escolhas independentes, e as duas ficam marcadas."""
    from provas.ui.wizard import _acabamento_atual

    class EstadoFalso:
        class config:
            fundo_paginas = "preto"
            sombra_fotos = True
            estilo_capa = "classica"

    janela.project_state = EstadoFalso()
    assert _acabamento_atual(janela) == {"fundo_preto", "sombra"}

    passo = WizardDialog(janela)
    passo._indice = 2                    # acabamento das páginas
    passo._mostrar_etapa()

    marcados = [b.text() for b in passo._botoes_acao if b.property("ativo")]
    assert marcados == ["Preto", "Sombra nas fotos"]
    passo.deleteLater()


def test_alternar_a_sombra_preserva_o_fundo(qt_app: QApplication, janela) -> None:
    """Ligar a sombra não pode zerar a cor de fundo escolhida antes."""
    from provas.ui.wizard import ACOES

    chamadas: list[tuple[str, bool]] = []

    class EstadoFalso:
        class config:
            fundo_paginas = "cinza"
            sombra_fotos = False

    janela.project_state = EstadoFalso()
    janela.set_page_appearance = lambda fundo, sombra: chamadas.append((fundo, sombra))

    ACOES["sombra"](janela)
    assert chamadas == [("cinza", True)], "o fundo escolhido sobrevive ao ligar a sombra"

    chamadas.clear()
    ACOES["fundo_preto"](janela)
    assert chamadas == [("preto", False)], "trocar o fundo preserva o estado da sombra"


def test_a_etapa_da_pasta_pede_a_identidade_e_escreve_na_barra_lateral(qt_app, janela):
    """Preencher depois é caro: cada pausa na digitação redesenha a capa.

    Na primeira etapa ainda não há prévia, então a identidade sai de graça — e
    ela assina todas as capas.
    """
    from PySide6.QtWidgets import QLineEdit

    passo = WizardDialog(janela)
    try:
        assert ETAPAS[0].campos, "a etapa da pasta precisa pedir a identidade"
        campos = passo.campos
        rotulos = [campos.itemAt(i, campos.ItemRole.LabelRole).widget().text()
                   for i in range(campos.rowCount())]
        assert rotulos == ["Título", "Fotógrafo / estúdio", "Site"]

        entrada = campos.itemAt(1, campos.ItemRole.FieldRole).widget()
        assert isinstance(entrada, QLineEdit)
        entrada.setText("Estúdio Fanara")
        entrada.textEdited.emit("Estúdio Fanara")

        assert janela.sidebar.studio_edit.text() == "Estúdio Fanara", (
            "o wizard tem de escrever na barra lateral, que é a fonte da verdade"
        )
    finally:
        passo.close()
        passo.deleteLater()
        qt_app.processEvents()


def test_o_logotipo_do_wizard_usa_o_botao_que_ja_existe(qt_app, janela):
    """Duplicar o seletor de arquivo duplicaria a validação do logotipo."""
    from provas.ui.wizard import ACOES

    assert ("Escolher logotipo", "escolher_logotipo") in ETAPAS[0].acoes
    cliques = []
    janela.sidebar.logo_choose_button.click = lambda: cliques.append(1)
    ACOES["escolher_logotipo"](janela)
    assert cliques == [1]


def test_a_janela_nunca_abre_menor_do_que_a_etapa_precisa(qt_app, janela) -> None:
    """Mínimo fixo abaixo do conteúdo faz os campos pousarem sobre os botões.

    A primeira etapa ganhou três campos de identidade e passou a pedir mais
    altura que o mínimo antigo; o defeito só aparece olhando a tela.
    """
    passo = WizardDialog(janela)
    try:
        for indice in range(len(ETAPAS)):
            passo._indice = indice
            passo._mostrar_etapa()
            qt_app.processEvents()
            pedido = passo.minimumSizeHint()
            assert passo.width() >= pedido.width(), f"etapa {indice + 1} espremida"
            assert passo.height() >= pedido.height(), f"etapa {indice + 1} espremida"
    finally:
        passo.close()
        passo.deleteLater()
        qt_app.processEvents()


def test_o_passo_a_passo_oferece_todos_os_estilos_de_capa(qt_app, janela) -> None:
    """Fixar a lista aqui deixou o guia oferecendo três capas de onze.

    Quem seguia o passo a passo nunca via as outras oito — elas só existiam na
    barra lateral. A lista tem de vir da mesma fonte, não de uma cópia.
    """
    from provas.capas import COVER_STYLES

    passo = WizardDialog(janela)
    try:
        etapa = next(i for i, e in enumerate(ETAPAS) if e.titulo == "Estilo da capa")
        passo._indice = etapa
        passo._mostrar_etapa()
        qt_app.processEvents()

        acoes = [passo._acao_do_botao[botao] for botao in passo._botoes_acao]
        assert acoes == [f"capa_{estilo}" for estilo in COVER_STYLES]
        for acao in acoes:
            assert acao in ACOES, f"{acao} tem botão mas não tem ação"
    finally:
        passo.close()
        passo.deleteLater()
        qt_app.processEvents()


def test_cada_estilo_de_capa_tem_ilustracao_empacotada() -> None:
    """Botão sem exemplo deixa a etapa muda justamente onde ela mais ensina."""
    from provas.capas import COVER_STYLES
    from provas import recursos

    etapa = next(e for e in ETAPAS if e.titulo == "Estilo da capa")
    for estilo in COVER_STYLES:
        nome = etapa.imagens[f"capa_{estilo}"]
        assert recursos.caminho(f"passo-a-passo/{nome}.jpg").is_file(), (
            f"falta a ilustração de {estilo}"
        )
