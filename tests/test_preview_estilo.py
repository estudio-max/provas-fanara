from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from provas.modelos import BookPlan, PagePlan
from provas.ui import PreviewGrid


@pytest.fixture
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _plano() -> BookPlan:
    paginas = tuple(
        PagePlan(numero, "solo-landscape", (f"page-{numero}.jpg",), "narrative")
        for numero in (1, 2)
    )
    return BookPlan(71, "fotolivro", ("cover.jpg",), paginas)


def _miniaturas(cor: str) -> tuple[Image.Image, ...]:
    return tuple(Image.new("RGB", (60, 42), cor) for _ in range(2))


def _cor_central(grade: PreviewGrid, indice: int) -> tuple[int, int, int]:
    imagem = grade._images[indice]
    pixel = imagem.pixelColor(imagem.width() // 2, imagem.height() // 2)
    return (pixel.red(), pixel.green(), pixel.blue())


def test_mudar_a_aparencia_troca_a_miniatura_do_mesmo_plano(qt_app: QApplication) -> None:
    """O fundo das páginas muda o pixel sem mudar o plano.

    A grade indexava as miniaturas só pelo plano, então devolvia a imagem
    anterior e a mudança de fundo nunca aparecia — apesar de o PDF sair certo.
    """
    grade = PreviewGrid()
    plano = _plano()

    grade.set_style_token(("branco", False))
    grade.set_previews(plano, _miniaturas("white"))
    assert _cor_central(grade, 0) == (255, 255, 255)

    grade.set_style_token(("preto", False))
    grade.set_previews(plano, _miniaturas("black"))
    assert _cor_central(grade, 0) == (0, 0, 0), (
        "com o mesmo plano e estilo novo, a grade tem de mostrar a miniatura nova"
    )

    grade.deleteLater()


def test_o_cache_da_grade_continua_valendo_quando_nada_muda(qt_app: QApplication) -> None:
    """A correção não pode custar o cache: mesmo plano e mesmo estilo reaproveitam."""
    grade = PreviewGrid()
    plano = _plano()

    grade.set_style_token(("branco", False))
    grade.set_previews(plano, _miniaturas("white"))
    primeira = grade._images[0]

    grade.set_previews(plano, _miniaturas("red"))
    assert grade._images[0] is primeira, "sem mudança de estilo, a imagem é reaproveitada"

    grade.deleteLater()


def _config(**mudancas):
    from provas.motor import Config

    base = dict(
        pasta=".", titulo="Título", subtitulo="Sub", estudio="Estúdio", site="site.com",
        modo="fotolivro", paisagem=True, girar_horizontais=False, semente=71,
        capa_mosaico=True, estilo_capa="mosaico",
    )
    return Config(**{**base, **mudancas}).com_padroes()


@pytest.mark.parametrize("campo,valor", [
    ("estilo_capa", "curvas_editoriais"),
    ("cor_fundo", "#402020"),
    ("subtitulo", "outro"),
    ("foto_capa_id", "outra.jpg"),
    ("capa_zoom", 2.0),
    ("capa_foco_x", 0.9),
    ("capa_foco_y", 0.9),
    ("capa_enquadramento", "manual"),
])
def test_campos_de_capa_nao_invalidam_a_previa_das_paginas(campo, valor):
    """Trocar a capa redesenhava o livro inteiro para atualizar uma imagem só.

    A assinatura descreve o que altera uma página interna; nenhum destes campos
    altera, e a renderização confirma isso — ver o comentário em
    `render_style_fingerprint`.
    """
    from provas.motor import render_style_fingerprint

    referencia = render_style_fingerprint(_config(), "fotolivro", 71)
    alterada = render_style_fingerprint(_config(**{campo: valor}), "fotolivro", 71)

    assert alterada == referencia, f"{campo} não desenha página interna, mas invalidou o cache"


@pytest.mark.parametrize("campo,valor", [
    ("fundo_paginas", "preto"),
    ("sombra_fotos", True),
    ("qualidade", "alta"),
    ("titulo", "outro"),
    ("estudio", "outro"),
])
def test_campos_da_pagina_continuam_invalidando_a_previa(campo, valor):
    """A poda não pode ir longe demais: o que desenha a página tem de invalidar."""
    from provas.motor import render_style_fingerprint

    referencia = render_style_fingerprint(_config(), "fotolivro", 71)
    alterada = render_style_fingerprint(_config(**{campo: valor}), "fotolivro", 71)

    assert alterada != referencia, f"{campo} altera a página e precisa invalidar o cache"


def test_o_cache_do_motor_nao_entrega_a_imagem_que_ele_guarda():
    """Fechar uma miniatura recebida não pode corromper o cache.

    O `gerar_preview` devolvia a própria imagem guardada; quem a fechasse deixava
    o cache com uma imagem morta, e o acerto seguinte estourava com
    "Operation on closed image" — que foi como este bug apareceu.
    """
    from provas import preview

    pagina = PagePlan(1, "single-landscape", ("foto.jpg",), "narrative")
    plano = BookPlan(71, "fotolivro", ("foto.jpg",), (pagina,))
    assets = {"foto.jpg": Image.new("RGB", (400, 300), "blue")}

    preview.clear_cache()
    preview.render_page_thumbnail(plano, 1, assets, 80).close()   # primeiro: cache miss

    # O acerto é que entregava a imagem do cache; fechá-la matava a guardada.
    preview.render_page_thumbnail(plano, 1, assets, 80).close()

    terceira = preview.render_page_thumbnail(plano, 1, assets, 80)
    terceira.load()  # estourava aqui: "Operation on closed image"
    assert terceira.width == 80
