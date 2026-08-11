"""Identidade visual do PDF: paleta derivada do fundo, fontes e medidas da página."""
from __future__ import annotations

import os
from dataclasses import dataclass
from types import MappingProxyType

Cor = tuple[float, float, float]

FUNDO_PADRAO = "#16161A"          # grafite
ACENTO_PADRAO = (0.847, 0.251, 0.376)   # #D84060, o rosa da marca
PAGE_BACKGROUNDS = MappingProxyType({
    "branco": "#FFFFFF",
    "cinza": "#D2D2D2",
    "preto": "#111215",
})


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


def _luminancia_wcag(cor: Cor) -> float:
    """Return relative luminance using WCAG's sRGB transfer curve."""
    canais = tuple(
        canal / 12.92 if canal <= 0.04045 else ((canal + 0.055) / 1.055) ** 2.4
        for canal in cor
    )
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def _contraste_wcag(a: Cor, b: Cor) -> float:
    clara, escura = sorted((_luminancia_wcag(a), _luminancia_wcag(b)), reverse=True)
    return (clara + 0.05) / (escura + 0.05)


def _tom_com_contraste(fundo: Cor, texto: Cor, minimo: float) -> Cor:
    """Mix toward ``texto`` until the WCAG contrast threshold is satisfied."""
    if _contraste_wcag(texto, fundo) < minimo:
        raise ValueError("A paleta não possui contraste suficiente.")
    baixo, alto = 0.0, 1.0
    for _ in range(32):
        meio = (baixo + alto) / 2
        if _contraste_wcag(_misturar(fundo, texto, meio), fundo) >= minimo:
            alto = meio
        else:
            baixo = meio
    return _misturar(fundo, texto, alto)


def _acento_com_contraste(fundo: Cor, acento: Cor, texto: Cor, minimo: float) -> Cor:
    """Keep the accent hue where possible, adapting it only for readable text."""
    if _contraste_wcag(acento, fundo) >= minimo:
        return acento
    baixo, alto = 0.0, 1.0
    for _ in range(32):
        meio = (baixo + alto) / 2
        candidato = _misturar(acento, texto, meio)
        if _contraste_wcag(candidato, fundo) >= minimo:
            alto = meio
        else:
            baixo = meio
    return _misturar(acento, texto, alto)


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


def paleta_paginas(nome: str) -> Paleta:
    """Resolve one of the supported internal-page backgrounds.

    The cover continues to own its independent ``cor_fundo`` palette.  Page
    presets strengthen secondary text and visual boundaries to their WCAG
    thresholds without changing the existing cover palette behaviour.
    """
    try:
        base = paleta(PAGE_BACKGROUNDS[nome])
    except (KeyError, TypeError) as exc:
        raise ValueError("Fundo das páginas inválido.") from exc
    return Paleta(
        fundo=base.fundo,
        painel=base.painel,
        texto=base.texto,
        apagado=_tom_com_contraste(base.fundo, base.texto, 4.5),
        filete=_tom_com_contraste(base.fundo, base.texto, 3.0),
        moldura=_tom_com_contraste(base.fundo, base.texto, 3.4),
        acento=_acento_com_contraste(base.fundo, base.acento, base.texto, 4.5),
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
