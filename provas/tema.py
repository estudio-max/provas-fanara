"""Identidade visual do PDF: paleta derivada do fundo, fontes e medidas da página."""
from __future__ import annotations

import os
from dataclasses import dataclass

Cor = tuple[float, float, float]

FUNDO_PADRAO = "#16161A"          # grafite
ACENTO_PADRAO = (0.847, 0.251, 0.376)   # #D84060, o rosa da marca


def ler_hex(texto: str) -> Cor:
    """'#16161A' -> (0.086, 0.086, 0.102). Devolve o padrão se o texto não servir."""
    limpo = (texto or "").strip().lstrip("#")
    if len(limpo) == 3:
        limpo = "".join(c * 2 for c in limpo)
    try:
        valor = int(limpo, 16)
    except ValueError:
        return ler_hex(FUNDO_PADRAO)
    if len(limpo) != 6:
        return ler_hex(FUNDO_PADRAO)
    return ((valor >> 16 & 255) / 255, (valor >> 8 & 255) / 255, (valor & 255) / 255)


def escrever_hex(cor: Cor) -> str:
    return "#" + "".join(f"{round(c * 255):02X}" for c in cor)


def _luminancia(cor: Cor) -> float:
    return 0.2126 * cor[0] + 0.7152 * cor[1] + 0.0722 * cor[2]


def _misturar(a: Cor, b: Cor, quanto: float) -> Cor:
    return tuple(x + (y - x) * quanto for x, y in zip(a, b))   # type: ignore[return-value]


@dataclass(frozen=True)
class Paleta:
    """Todas as cores do documento, derivadas do fundo escolhido.

    Assim um fundo claro vira automaticamente um tema claro: o texto inverte e
    os cinzas intermediários são recalculados por mistura com o fundo.
    """
    fundo: Cor
    painel: Cor
    texto: Cor
    apagado: Cor
    filete: Cor
    moldura: Cor
    acento: Cor

    @property
    def claro(self) -> bool:
        return _luminancia(self.fundo) > 0.5

    @property
    def fundo_rgb(self) -> tuple[int, int, int]:
        return tuple(round(c * 255) for c in self.fundo)   # type: ignore[return-value]


def paleta(fundo_hex: str = FUNDO_PADRAO, acento: Cor = ACENTO_PADRAO) -> Paleta:
    fundo = ler_hex(fundo_hex)
    claro = _luminancia(fundo) > 0.5
    texto = (0.11, 0.11, 0.13) if claro else (0.925, 0.925, 0.945)
    return Paleta(
        fundo=fundo,
        painel=_misturar(fundo, texto, 0.03),
        texto=texto,
        # cinza claro sobre papel some; no tema claro o secundário fecha mais
        apagado=_misturar(fundo, texto, 0.70 if claro else 0.62),
        filete=_misturar(fundo, texto, 0.11),
        moldura=_misturar(fundo, texto, 0.16),
        acento=acento,
    )


# --- fontes ---------------------------------------------------------------
# Cada papel tipográfico é procurado no sistema, do preferido ao aceitável. Não
# achando nada, cai para uma das fontes que todo PDF já entende (base 14) — o
# documento perde requinte, mas nunca deixa de ser gerado.

@dataclass(frozen=True)
class Fonte:
    arquivo: str | None      # caminho de um TTF/OTF do sistema
    embutida: str            # nome base 14 do PDF, usado quando não há arquivo


def _pastas_de_fontes() -> list[str]:
    import sys
    if sys.platform == "win32":
        return [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")]
    if sys.platform == "darwin":
        return ["/System/Library/Fonts/Supplemental", "/System/Library/Fonts",
                "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    return ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype",
            "/usr/share/fonts", "/usr/local/share/fonts",
            os.path.expanduser("~/.local/share/fonts")]


def _procurar(*nomes: str) -> str | None:
    for pasta in _pastas_de_fontes():
        for nome in nomes:
            caminho = os.path.join(pasta, nome)
            if os.path.exists(caminho):
                return caminho
    return None


# nomes do Windows primeiro, depois os equivalentes do macOS, depois Linux
SERIF = Fonte(_procurar("constan.ttf", "georgia.ttf",
                        "Georgia.ttf", "Times New Roman.ttf", "Baskerville.ttc",
                        "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf"), "tiro")
SERIF_ITALICO = Fonte(_procurar("constani.ttf", "georgiai.ttf",
                                "Georgia Italic.ttf", "Times New Roman Italic.ttf",
                                "DejaVuSerif-Italic.ttf", "LiberationSerif-Italic.ttf"), "tiit")
SANS = Fonte(_procurar("segoeuil.ttf", "segoeui.ttf",
                       "Trebuchet MS.ttf", "Verdana.ttf", "Arial.ttf",
                       "DejaVuSans.ttf", "LiberationSans-Regular.ttf"), "helv")
SANS_MEDIO = Fonte(_procurar("seguisb.ttf", "segoeui.ttf",
                             "Trebuchet MS Bold.ttf", "Verdana Bold.ttf", "Arial Bold.ttf",
                             "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"), "hebo")

# --- página ---------------------------------------------------------------
A4 = (595.28, 841.89)
A4_PAISAGEM = (841.89, 595.28)

MARGEM_LATERAL = 40.0
TOPO_CABECALHO = 28.0        # topo do logotipo do cabeçalho
ALTURA_CABECALHO = 17.0
Y_FILETE_TOPO = 60.0
Y_CONTEUDO = 76.0            # onde a grade começa
ALTURA_RODAPE = 40.0         # reservado embaixo (filete + textos)

VAO_X = 14.0                 # respiro entre colunas
VAO_Y = 16.0                 # respiro entre linhas
ALTURA_LEGENDA = 19.0        # faixa do nome do arquivo dentro do cartão
RESPIRO_CARTAO = 7.0         # margem interna do cartão em volta da foto
