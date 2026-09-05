from __future__ import annotations

import pytest
from PIL import Image

from provas import cor_capa
from provas.capas_editoriais import ESTILOS_EDITORIAIS
from provas.tipografia_capas import PARES, familias_ausentes, par

LARGURA, ALTURA = 842, 595       # A4 paisagem, a medida do guia


def _fotos(quantidade: int = 4) -> list[Image.Image]:
    """Fotografias sintéticas com cores distintas, para as peças se distinguirem."""
    cores = ((190, 70, 60), (60, 120, 190), (90, 160, 90), (200, 170, 80))
    return [Image.new("RGB", (900, 600) if indice % 2 else (600, 900), cores[indice % 4])
            for indice in range(quantidade)]


@pytest.mark.parametrize("nome", sorted(ESTILOS_EDITORIAIS))
def test_cada_estilo_entrega_a_capa_no_tamanho_pedido(nome: str) -> None:
    funcao, multiplas = ESTILOS_EDITORIAIS[nome]
    fotos = _fotos()
    arte = funcao(fotos if multiplas else fotos[0], LARGURA, ALTURA,
                  "O silêncio da viagem", "Uma jornada pelas paisagens")

    assert arte.imagem.size == (LARGURA, ALTURA)
    assert arte.imagem.mode == "RGB"


@pytest.mark.parametrize("nome", sorted(ESTILOS_EDITORIAIS))
def test_cada_estilo_desenha_o_texto_na_propria_arte(nome: str) -> None:
    """A capa editorial embute a tipografia; sem isso o título sumiria."""
    funcao, multiplas = ESTILOS_EDITORIAIS[nome]
    fotos = _fotos()
    entrada = fotos if multiplas else fotos[0]
    com_texto = funcao(entrada, LARGURA, ALTURA, "Fragmentos", "Subtítulo")
    sem_texto = funcao(entrada, LARGURA, ALTURA, "", "")

    assert com_texto.imagem.tobytes() != sem_texto.imagem.tobytes()


@pytest.mark.parametrize("nome", sorted(ESTILOS_EDITORIAIS))
def test_estilos_de_varias_fotos_aceitam_uma_so(nome: str) -> None:
    """Ensaio curto não pode quebrar a capa: as peças repetem a foto disponível."""
    funcao, multiplas = ESTILOS_EDITORIAIS[nome]
    uma = _fotos(1)
    arte = funcao(uma if multiplas else uma[0], LARGURA, ALTURA, "Título", "")

    assert arte.imagem.size == (LARGURA, ALTURA)


@pytest.mark.parametrize("nome", sorted(ESTILOS_EDITORIAIS))
def test_medidas_invalidas_falham_alto(nome: str) -> None:
    funcao, multiplas = ESTILOS_EDITORIAIS[nome]
    fotos = _fotos()
    with pytest.raises(ValueError):
        funcao(fotos if multiplas else fotos[0], 0, ALTURA, "Título", "")


def test_titulo_longo_encolhe_em_vez_de_transbordar() -> None:
    """O corpo cede antes de a capa estourar — mas a capa sai do mesmo tamanho."""
    from provas.capas_editoriais import jornada

    curto = jornada(_fotos(1)[0], LARGURA, ALTURA, "Sol", "")
    longo = jornada(_fotos(1)[0], LARGURA, ALTURA,
                    "Um título absurdamente longo que jamais caberia na coluna", "")

    assert curto.imagem.size == longo.imagem.size == (LARGURA, ALTURA)


# --- cor extraída ---------------------------------------------------------

def test_foto_acromatica_cai_no_grafite() -> None:
    """Inventar cor onde não há seria pior que não ter."""
    cinza = Image.new("RGB", (200, 200), (128, 128, 128))

    assert cor_capa.cor_dominante(cinza) is None
    assert cor_capa.fundo_da_capa(cinza) == cor_capa.GRAFITE
    assert cor_capa.fundo_claro_da_capa(cinza) == cor_capa.MARFIM


def test_a_cor_do_fundo_nasce_da_matiz_da_foto() -> None:
    import colorsys

    azul = Image.new("RGB", (200, 200), (30, 90, 200))
    fundo = cor_capa.fundo_da_capa(azul)
    matiz_foto = colorsys.rgb_to_hsv(30 / 255, 90 / 255, 200 / 255)[0]
    matiz_fundo = colorsys.rgb_to_hsv(*(canal / 255 for canal in fundo))[0]

    assert matiz_fundo == pytest.approx(matiz_foto, abs=0.04)
    assert cor_capa.cor_do_texto(fundo) == (250, 250, 252), "fundo escuro pede texto claro"


def test_o_texto_troca_de_cor_conforme_o_fundo() -> None:
    assert cor_capa.cor_do_texto((250, 248, 244)) == (24, 25, 29)
    assert cor_capa.cor_do_texto((28, 30, 36)) == (250, 250, 252)


# --- tipografia -----------------------------------------------------------

@pytest.mark.parametrize("nome", sorted(PARES))
def test_todo_par_resolve_alguma_fonte(nome: str) -> None:
    """Família ausente cai na substituta; a capa nunca fica sem tipografia."""
    combinacao = par(nome)

    assert combinacao.titulo.arquivo or combinacao.titulo.embutida
    assert combinacao.subtitulo.arquivo or combinacao.subtitulo.embutida


def test_par_desconhecido_falha_com_as_opcoes() -> None:
    with pytest.raises(ValueError, match="Par tipográfico desconhecido"):
        par("inventado")


def test_o_diagnostico_lista_o_que_falta_empacotar() -> None:
    """Serve para saber se a capa está saindo com a fonte certa ou com a reserva."""
    ausentes = familias_ausentes()

    assert isinstance(ausentes, tuple)
    assert all(nome.endswith(".ttf") for nome in ausentes)


def test_a_barra_lateral_oferece_exatamente_os_estilos_do_motor() -> None:
    """Um estilo sem entrada é inalcançável; uma entrada sem estilo quebra ao clicar."""
    from provas.capas import COVER_STYLES
    from provas.ui.sidebar import ESTILOS_DE_CAPA

    oferecidos = [chave for _rotulo, chave in ESTILOS_DE_CAPA]

    assert oferecidos == list(COVER_STYLES)
    assert len({rotulo for rotulo, _ in ESTILOS_DE_CAPA}) == len(ESTILOS_DE_CAPA)


@pytest.mark.parametrize("estilo", sorted(ESTILOS_EDITORIAIS))
def test_o_motor_monta_cada_estilo_editorial(estilo: str) -> None:
    """Da chave à arte: o caminho que o aplicativo percorre ao trocar a capa."""
    from provas import capas
    from provas.identidade_capa import IdentityData

    fotos = [capas.CoverPhoto(str(indice), imagem)
             for indice, imagem in enumerate(_fotos())]
    capa = capas.gerar(estilo, fotos, LARGURA, ALTURA, None,
                       identity=IdentityData("Título", "Estúdio", "site", ""),
                       subtitulo="Subtítulo")

    assert capa.imagem.size == (LARGURA, ALTURA)
    assert capa.identity_embedded, "o estilo editorial desenha o próprio texto"


def test_estilo_editorial_sem_identidade_falha_claro() -> None:
    from provas import capas

    with pytest.raises(ValueError, match="exige os dados de identidade"):
        capas.gerar("jornada", _fotos(), LARGURA, ALTURA, None)
