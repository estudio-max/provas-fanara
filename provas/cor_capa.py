"""Cor de fundo da capa, tirada da própria fotografia.

Uma capa com cor sólida só funciona quando a cor conversa com a foto. Em vez de
pedir que o fotógrafo escolha, a cor é extraída da imagem e ajustada até ficar
escura e sóbria o bastante para o texto pousar em cima.

Fotografia acromática — preto e branco, neblina, neve — não tem cor a extrair.
Nesse caso a capa cai no grafite do tema, que é o comportamento certo: inventar
uma cor onde não há seria pior que não ter.
"""
from __future__ import annotations

import colorsys

from PIL import Image

#: Abaixo disto a imagem é considerada acromática e não há cor a extrair.
_SATURACAO_MINIMA = 0.12
#: A cor de fundo é levada a esta faixa de luminosidade, para o texto claro ler.
_LUMINOSIDADE_ALVO = 0.26
#: Cor sóbria demais cansa; saturada demais briga com a foto.
_SATURACAO_ALVO = 0.42
#: Grafite do tema, usado quando a fotografia não tem cor.
GRAFITE = (28, 30, 36)

_AMOSTRA = 72          # a imagem é reduzida a isto antes de contar cores
_CORES = 8             # quantas cores a quantização procura


def _luminancia(cor: tuple[int, int, int]) -> float:
    vermelho, verde, azul = (canal / 255 for canal in cor)
    return 0.2126 * vermelho + 0.7152 * verde + 0.0722 * azul


def cor_dominante(imagem: Image.Image) -> tuple[int, int, int] | None:
    """A cor mais presente na fotografia, ou None se ela for acromática.

    Pixels quase pretos ou quase brancos são descartados: eles dominam a
    contagem em qualquer foto e não dizem nada sobre a cor da imagem.
    """
    reduzida = imagem.convert("RGB").copy()
    reduzida.thumbnail((_AMOSTRA, _AMOSTRA), Image.LANCZOS)
    paleta = reduzida.quantize(colors=_CORES, method=Image.Quantize.MEDIANCUT)
    cores = paleta.convert("RGB").getcolors(_AMOSTRA * _AMOSTRA) or []

    melhor: tuple[float, tuple[int, int, int]] | None = None
    for contagem, cor in cores:
        matiz, saturacao, valor = colorsys.rgb_to_hsv(*(canal / 255 for canal in cor))
        if saturacao < _SATURACAO_MINIMA or valor < 0.12 or valor > 0.94:
            continue
        # Peso pela presença e pela saturação: uma cor pouco presente mas viva
        # descreve a foto melhor que um cinza levemente colorido que cobre tudo.
        peso = contagem * (0.4 + saturacao)
        if melhor is None or peso > melhor[0]:
            melhor = (peso, cor)
    return melhor[1] if melhor else None


def fundo_da_capa(imagem: Image.Image) -> tuple[int, int, int]:
    """Cor sólida para a capa, derivada da fotografia e pronta para texto claro."""
    dominante = cor_dominante(imagem)
    if dominante is None:
        return GRAFITE

    matiz, saturacao, _valor = colorsys.rgb_to_hsv(*(canal / 255 for canal in dominante))
    saturacao = min(saturacao, _SATURACAO_ALVO)
    vermelho, verde, azul = colorsys.hsv_to_rgb(matiz, saturacao, _LUMINOSIDADE_ALVO * 1.7)
    return tuple(round(canal * 255) for canal in (vermelho, verde, azul))


def cor_do_texto(fundo: tuple[int, int, int]) -> tuple[int, int, int]:
    """Branco ou grafite, o que ler melhor sobre o fundo.

    O limiar de 0.45 é mais alto que o meio-termo de propósito: sobre uma cor
    saturada, o texto claro lê bem antes do ponto em que a matemática pura
    mandaria trocar.
    """
    return (250, 250, 252) if _luminancia(fundo) < 0.45 else (24, 25, 29)


#: Fundos claros do guia — creme, bege, cinza — nascem da mesma matiz da foto.
_CLARO_LUMINOSIDADE = 0.94
_CLARO_SATURACAO = 0.045
MARFIM = (247, 245, 240)


def fundo_claro_da_capa(imagem: Image.Image) -> tuple[int, int, int]:
    """Tom claro para capas de campo neutro, tingido pela matiz da fotografia.

    O guia pede creme, bege ou cinza conforme o estilo. Derivar o tom da foto
    faz o creme sair quente numa fotografia quente e frio numa fria, sem que
    ninguém precise escolher.
    """
    dominante = cor_dominante(imagem)
    if dominante is None:
        return MARFIM
    matiz, _saturacao, _valor = colorsys.rgb_to_hsv(*(canal / 255 for canal in dominante))
    canais = colorsys.hsv_to_rgb(matiz, _CLARO_SATURACAO, _CLARO_LUMINOSIDADE)
    return tuple(round(canal * 255) for canal in canais)
