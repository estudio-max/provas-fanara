"""Leitura das fotos da sessão, orientação, marca d'água e miniaturas."""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageOps

from . import raw, tema

EXTENSOES_JPG = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}

# orientação Exif -> transposições do Pillow
_TRANSPOSICOES = {
    2: (Image.Transpose.FLIP_LEFT_RIGHT,),
    3: (Image.Transpose.ROTATE_180,),
    4: (Image.Transpose.FLIP_TOP_BOTTOM,),
    5: (Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.ROTATE_90),
    6: (Image.Transpose.ROTATE_270,),
    7: (Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.ROTATE_270),
    8: (Image.Transpose.ROTATE_90,),
}


@dataclass(frozen=True)
class Foto:
    caminho: str
    rotulo: str          # nome exibido ao cliente, sem extensão

    @property
    def e_raw(self) -> bool:
        return raw.e_raw(self.caminho)


def _chave_natural(texto: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", texto)]


def listar_fotos(pasta: str, recursivo: bool = False) -> list[Foto]:
    """Lista as fotos da pasta, uma por captura.

    Quando a câmera gravou RAW + JPG, os dois arquivos têm o mesmo nome-base e
    representam a mesma foto: o JPG vence, porque já vem revelado pela câmera.
    """
    encontrados: dict[str, str] = {}
    caminhador = os.walk(pasta) if recursivo else [(pasta, [], os.listdir(pasta))]
    for raiz, _, arquivos in caminhador:
        if os.path.basename(raiz).lower().endswith(".lrdata"):
            continue
        for nome in arquivos:
            base, ext = os.path.splitext(nome)
            ext = ext.lower()
            e_jpg = ext in EXTENSOES_JPG
            if not e_jpg and ext not in raw.EXTENSOES:
                continue
            chave = os.path.join(os.path.relpath(raiz, pasta), base).lower()
            atual = encontrados.get(chave)
            if atual is None or (e_jpg and raw.e_raw(atual)):
                encontrados[chave] = os.path.join(raiz, nome)

    fotos = [Foto(caminho, os.path.splitext(os.path.basename(caminho))[0])
             for caminho in encontrados.values()]
    fotos.sort(key=lambda f: _chave_natural(f.rotulo))
    return fotos


def abrir(foto: Foto) -> Image.Image:
    """Abre a foto já na orientação correta, em RGB."""
    if foto.e_raw:
        dados, orientacao = raw.extrair_previa(foto.caminho)
        if dados is None:
            raise ValueError(f"{os.path.basename(foto.caminho)}: RAW sem pré-visualização embutida")
        imagem = Image.open(io.BytesIO(dados))
        imagem.load()
        imagem = imagem.convert("RGB")
        # a prévia costuma vir na orientação bruta do sensor
        for transposicao in _TRANSPOSICOES.get(orientacao, ()):
            imagem = imagem.transpose(transposicao)
        return imagem

    imagem = Image.open(foto.caminho)
    imagem = ImageOps.exif_transpose(imagem)
    return imagem.convert("RGB")


def redimensionar(imagem: Image.Image, maior_lado: int) -> Image.Image:
    """Reduz proporcionalmente para que o maior lado tenha `maior_lado` px."""
    largura, altura = imagem.size
    atual = max(largura, altura)
    if atual <= maior_lado:
        return imagem
    escala = maior_lado / atual
    novo = (max(1, round(largura * escala)), max(1, round(altura * escala)))
    return imagem.resize(novo, Image.Resampling.LANCZOS)


def recortar_para_preencher(imagem: Image.Image, largura: int, altura: int,
                            centro: tuple[float, float] = (0.5, 0.34)) -> Image.Image:
    """Recorta para preencher exatamente largura x altura.

    O recorte puxa para cima do centro geométrico porque em retrato o interesse
    (rosto) fica no terço superior.
    """
    return ImageOps.fit(imagem, (largura, altura), Image.Resampling.LANCZOS, centering=centro)


# --- logotipo -------------------------------------------------------------

def carregar_logo(caminho: str) -> Image.Image:
    """Carrega o logotipo em RGBA, garantindo canal alfa útil."""
    logo = Image.open(caminho).convert("RGBA")
    alfa = logo.getchannel("A")
    if alfa.getextrema()[0] == 255:
        # PNG sem transparência real: o fundo branco vira o recorte
        cinza = logo.convert("L")
        logo.putalpha(ImageChops.invert(cinza).point(lambda v: min(255, int(v * 1.6))))
    caixa = logo.getchannel("A").getbbox()      # tira a margem vazia em volta
    return logo.crop(caixa) if caixa else logo


def logo_bicolor(logo: Image.Image) -> Image.Image:
    """Mantém o rosa da marca e transforma o preto em branco (para fundo escuro)."""
    r, _, b, alfa = logo.split()
    mascara_rosa = ImageChops.subtract(r, b).point(lambda v: 255 if v > 40 else 0)
    branco = Image.new("RGBA", logo.size, (255, 255, 255, 255))
    resultado = Image.composite(logo, branco, mascara_rosa)
    resultado.putalpha(alfa)
    return resultado


def logo_branco(logo: Image.Image) -> Image.Image:
    """Silhueta branca do logotipo, usada como marca d'água."""
    branco = Image.new("RGBA", logo.size, (255, 255, 255, 255))
    branco.putalpha(logo.getchannel("A"))
    return branco


def aplicar_marca_dagua(imagem: Image.Image, logo_alvo: Image.Image,
                        largura_relativa: float = 0.62, opacidade: float = 0.20) -> Image.Image:
    """Grava a marca d'água no centro da foto (fica na imagem, não no PDF)."""
    if opacidade <= 0:
        return imagem
    largura = max(1, round(imagem.width * largura_relativa))
    altura = max(1, round(logo_alvo.height * largura / logo_alvo.width))
    if altura > imagem.height * 0.6:
        altura = round(imagem.height * 0.6)
        largura = max(1, round(logo_alvo.width * altura / logo_alvo.height))
    marca = logo_alvo.resize((largura, altura), Image.Resampling.LANCZOS)
    alfa = marca.getchannel("A").point(lambda v: round(v * opacidade))
    marca.putalpha(alfa)

    base = imagem.convert("RGBA")
    posicao = ((base.width - largura) // 2, (base.height - altura) // 2)
    base.alpha_composite(marca, posicao)
    return base.convert("RGB")


# --- mosaico da capa ------------------------------------------------------

def montar_mosaico(miniaturas: list[Image.Image], largura: int, altura: int,
                   paleta: tema.Paleta, vao: int = 3) -> Image.Image:
    """Monta o mosaico de capa preenchendo a página inteira com todas as fotos."""
    total = max(1, len(miniaturas))
    proporcao = largura / altura
    melhor_colunas, menor_desperdicio = 1, None
    for colunas in range(1, total + 1):
        linhas = -(-total // colunas)
        celula = (largura / colunas) / (altura / linhas)
        desperdicio = abs(celula / proporcao - 1) + (colunas * linhas - total) / total
        if menor_desperdicio is None or desperdicio < menor_desperdicio:
            melhor_colunas, menor_desperdicio = colunas, desperdicio
    colunas = melhor_colunas
    linhas = -(-total // colunas)

    tela = Image.new("RGB", (largura, altura), paleta.fundo_rgb)
    altura_celula = (altura - vao * (linhas - 1)) / linhas
    for linha in range(linhas):
        na_linha = min(colunas, total - linha * colunas)
        if na_linha <= 0:
            break
        # a última fileira divide a largura inteira entre as fotos que sobraram,
        # para o mosaico nunca terminar com um buraco no canto
        largura_celula = (largura - vao * (na_linha - 1)) / na_linha
        y = round(linha * (altura_celula + vao))
        altura_px = round(altura_celula) if linha < linhas - 1 else altura - y
        for coluna in range(na_linha):
            x = round(coluna * (largura_celula + vao))
            largura_px = round(largura_celula) if coluna < na_linha - 1 else largura - x
            if largura_px <= 0 or altura_px <= 0:
                continue
            miniatura = miniaturas[linha * colunas + coluna]
            tela.paste(recortar_para_preencher(miniatura, largura_px, altura_px), (x, y))
    return tela


def veu_para_texto(mosaico: Image.Image, paleta: tema.Paleta,
                   opacidade_base: float | None = None) -> Image.Image:
    """Aplica um véu da cor do fundo para o texto da capa respirar sobre o mosaico.

    O véu é uniforme e ganha reforço na faixa central (logotipo e título) e no
    rodapé (chamada), que é onde a tipografia cai. Em tema claro ele clareia a
    imagem, pelo mesmo motivo que no escuro ele escurece.
    """
    # no tema claro o véu chapa a foto rápido demais; o reforço das faixas já
    # garante o contraste onde o texto cai, então a base pode ser mais leve
    if opacidade_base is None:
        opacidade_base = 0.50 if paleta.claro else 0.58
    veu = Image.new("L", (1, mosaico.height))
    desenho = ImageDraw.Draw(veu)
    for y in range(mosaico.height):
        posicao = y / max(1, mosaico.height - 1)
        reforco = 0.0
        for centro, alcance, peso in ((0.44, 0.26, 0.26), (0.90, 0.14, 0.20)):
            distancia = abs(posicao - centro) / alcance
            if distancia < 1:
                reforco = max(reforco, peso * (1 - distancia * distancia))
        desenho.point((0, y), fill=round(min(1.0, opacidade_base + reforco) * 255))
    veu = veu.resize(mosaico.size)
    chapado = Image.new("RGB", mosaico.size, paleta.fundo_rgb)
    return Image.composite(chapado, mosaico, veu)
