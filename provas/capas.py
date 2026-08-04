"""Estilos de capa: composições feitas com as fotos da própria sessão."""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from . import imagens, tema

ESTILOS = ("mosaico", "losango", "destaque")

SUPERAMOSTRAGEM = 3          # desenha a máscara ampliada e reduz, para borda lisa


@dataclass(frozen=True)
class Capa:
    imagem: Image.Image
    ancora: float            # altura relativa (0..1) onde o bloco de texto começa


def _amostrar(itens: list, quantidade: int) -> list:
    """Escolhe `quantidade` itens distribuídos ao longo da lista inteira.

    Quando a malha tem mais células do que fotos, as fotos se repetem — mas
    percorridas em passo largo, para que cópias não caiam lado a lado.
    """
    total = len(itens)
    if total == 0:
        return []
    if quantidade <= total:
        passo = total / quantidade
        return [itens[min(total - 1, int(i * passo))] for i in range(quantidade)]
    passo = next((p for p in range(max(2, total // 3), total)
                  if math.gcd(p, total) == 1), 1)
    return [itens[(i * passo) % total] for i in range(quantidade)]


def _mascara_losango(largura: int, altura: int, vao: float) -> Image.Image:
    """Máscara suave de um losango inscrito, encolhido por `vao` pixels."""
    escala = SUPERAMOSTRAGEM
    mascara = Image.new("L", (largura * escala, altura * escala), 0)
    meia_largura = largura * escala / 2
    meia_altura = altura * escala / 2
    recuo = vao * escala
    ImageDraw.Draw(mascara).polygon(
        [(meia_largura, recuo), (largura * escala - recuo, meia_altura),
         (meia_largura, altura * escala - recuo), (recuo, meia_altura)], fill=255)
    return mascara.resize((largura, altura), Image.Resampling.LANCZOS)


def _centros_losango(largura: int, altura: int, passo_x: float, passo_y: float):
    """Centros de uma malha de losangos que cobre a página inteira."""
    linha = -1
    while (linha - 1) * passo_y / 2 <= altura:
        y = linha * passo_y / 2
        deslocamento = 0.0 if linha % 2 == 0 else passo_x / 2
        coluna = -1
        while (coluna - 1) * passo_x + deslocamento <= largura:
            yield (coluna * passo_x + deslocamento, y)
            coluna += 1
        linha += 1


def _malha_losangos(quantidade: int, largura: int, altura: int,
                    proporcao: float = 1.0) -> tuple[list, float, float]:
    """Escolhe o tamanho do losango cuja malha chega mais perto de `quantidade`.

    Abaixo de 3 colunas os losangos ficam grandes demais e o recorte engole a
    foto, então essa é a malha mais grossa permitida.
    """
    melhor = None
    for colunas in range(3, 26):
        passo_x = largura / colunas
        passo_y = passo_x * proporcao
        centros = list(_centros_losango(largura, altura, passo_x, passo_y))
        distancia = abs(len(centros) - quantidade)
        if melhor is None or distancia < melhor[0]:
            melhor = (distancia, centros, passo_x, passo_y)
    _, centros, passo_x, passo_y = melhor
    return centros, passo_x, passo_y


def _colar_losango(tela: Image.Image, miniatura: Image.Image, centro: tuple[float, float],
                   passo_x: float, passo_y: float, vao: float) -> None:
    largura = max(2, round(passo_x))
    altura = max(2, round(passo_y))
    x = round(centro[0] - largura / 2)
    y = round(centro[1] - altura / 2)
    # recorte alto: no losango a parte visível é a faixa do meio, onde o rosto deve cair
    recorte = imagens.recortar_para_preencher(miniatura, largura, altura, centro=(0.5, 0.12))
    tela.paste(recorte, (x, y), _mascara_losango(largura, altura, vao))


def _mosaico(miniaturas: list[Image.Image], largura: int, altura: int,
             paleta: tema.Paleta) -> Image.Image:
    return imagens.montar_mosaico(miniaturas, largura, altura, paleta)


def gerar_mosaico_editorial(items: list[Image.Image], width: int, height: int,
                            palette: tema.Paleta) -> Capa:
    """Render a crop-to-fill cover mosaic with a calm, solid title field.

    Unlike internal pages, cover cells may crop.  The reserved field is kept
    untextured so title rendering needs no decorative mask or contrast guess.
    """
    if width <= 0 or height <= 0:
        raise ValueError("Cover dimensions must be positive")
    anchor = 0.72
    mosaic_height = max(1, round(height * 0.66))
    canvas = Image.new("RGB", (width, height), palette.fundo_rgb)
    if items:
        mosaic = imagens.montar_mosaico(items, width, mosaic_height, palette)
        canvas.paste(mosaic, (0, 0))
    return Capa(canvas, anchor)


def _losango(miniaturas: list[Image.Image], largura: int, altura: int,
             paleta: tema.Paleta) -> Image.Image:
    centros, passo_x, passo_y = _malha_losangos(len(miniaturas), largura, altura)
    escolhidas = _amostrar(miniaturas, len(centros))
    tela = Image.new("RGB", (largura, altura), paleta.fundo_rgb)
    vao = 1.5
    for miniatura, centro in zip(escolhidas, centros):
        _colar_losango(tela, miniatura, centro, passo_x, passo_y, vao)
    return tela


def _destaque(miniaturas: list[Image.Image], largura: int, altura: int,
              heroi: Image.Image, paleta: tema.Paleta) -> Image.Image:
    """Mosaico esmaecido com um losango grande, aceso, no centro."""
    fundo = imagens.veu_para_texto(_mosaico(miniaturas, largura, altura, paleta),
                                   paleta, opacidade_base=0.66)
    lado_x = round(largura * 0.62)
    lado_y = round(lado_x * 1.06)
    if lado_y > altura * 0.50:
        lado_y = round(altura * 0.50)
        lado_x = round(lado_y / 1.06)
    centro = (largura // 2, round(altura * 0.36))

    # o filete é um losango um pouco maior colado por baixo da foto
    borda = max(2, round(largura * 0.0035))
    largura_borda, altura_borda = lado_x + 2 * borda, lado_y + 2 * borda
    cor_borda = (28, 28, 32) if paleta.claro else (236, 237, 240)
    fundo.paste(Image.new("RGB", (largura_borda, altura_borda), cor_borda),
                (centro[0] - largura_borda // 2, centro[1] - altura_borda // 2),
                _mascara_losango(largura_borda, altura_borda, 0))

    recorte = imagens.recortar_para_preencher(heroi, lado_x, lado_y, centro=(0.5, 0.32))
    fundo.paste(recorte, (centro[0] - lado_x // 2, centro[1] - lado_y // 2),
                _mascara_losango(lado_x, lado_y, 0))
    return fundo


def gerar(estilo: str, miniaturas: list[Image.Image], largura: int, altura: int,
          paleta: tema.Paleta) -> Capa:
    """Monta a capa no estilo pedido e diz onde o texto deve começar."""
    if estilo == "losango":
        return Capa(imagens.veu_para_texto(_losango(miniaturas, largura, altura, paleta),
                                           paleta), 0.34)
    if estilo == "destaque":
        heroi = miniaturas[len(miniaturas) // 2]
        return Capa(_destaque(miniaturas, largura, altura, heroi, paleta), 0.62)
    return gerar_mosaico_editorial(miniaturas, largura, altura, paleta)
