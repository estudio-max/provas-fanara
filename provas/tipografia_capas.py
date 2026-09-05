"""Pares tipográficos das capas.

O guia de capas agrupa título e subtítulo em combinações fechadas — nunca uma
mistura livre de fontes. Cada preset abaixo é uma dessas combinações, e cada
estilo de capa escolhe um.

A fonte é procurada em três lugares, nesta ordem: o arquivo empacotado com o
aplicativo, uma família equivalente instalada no sistema, e por fim a fonte
padrão do Pillow. Assim uma família que ainda não foi empacotada não quebra a
capa — ela sai com a substituta, e o layout continua o mesmo.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import recursos, tema


def _empacotada(nome: str) -> str | None:
    """Caminho de uma fonte que viaja dentro do aplicativo, se ela existir."""
    caminho = recursos.caminho(f"fonts/{nome}")
    return str(caminho) if caminho.is_file() else None


def _fonte(empacotada: str, *sistema: str) -> tema.Fonte:
    """Prefere o arquivo empacotado; sem ele, cai para o equivalente do sistema."""
    return tema.Fonte(_empacotada(empacotada) or tema._procurar(*sistema), "helv")


@dataclass(frozen=True)
class ParTipografico:
    """Título e subtítulo de um estilo, com o tratamento de cada um."""

    nome: str
    titulo: tema.Fonte
    subtitulo: tema.Fonte
    titulo_caixa_alta: bool = True
    #: Entreletra do título, em ems. Caixa alta pede mais respiro.
    titulo_entreletra: float = 0.02
    subtitulo_caixa_alta: bool = False
    subtitulo_entreletra: float = 0.0

    @property
    def completo(self) -> bool:
        """Se as duas fontes desejadas foram encontradas."""
        return bool(self.titulo.arquivo and self.subtitulo.arquivo)


#: As quatro combinações do guia. O nome é o que aparece para quem escolhe.
PARES: dict[str, ParTipografico] = {
    "geometrico": ParTipografico(
        "Geométrico moderno",
        _fonte("Montserrat-Bold.ttf", "seguisb.ttf", "segoeui.ttf", "Arial Bold.ttf"),
        _fonte("Montserrat-Light.ttf", "segoeuil.ttf", "segoeui.ttf", "Arial.ttf"),
        titulo_entreletra=0.06,
    ),
    "editorial": ParTipografico(
        "Editorial de luxo",
        _fonte("PlayfairDisplay-BoldItalic.ttf", "constani.ttf", "georgiai.ttf",
               "Georgia Italic.ttf"),
        _fonte("CrimsonText-Regular.ttf", "pala.ttf", "constan.ttf", "georgia.ttf"),
        titulo_caixa_alta=False,
        titulo_entreletra=0.0,
    ),
    "condensado": ParTipografico(
        "Urbano condensado",
        _fonte("BebasNeue-Regular.ttf", "bahnschrift.ttf", "impact.ttf",
               "Franklin Gothic Medium.ttf"),
        _fonte("Lato-Light.ttf", "segoeuil.ttf", "segoeui.ttf", "Arial.ttf"),
        titulo_entreletra=0.04,
    ),
    "narrativo": ParTipografico(
        "Narrativo clássico",
        _fonte("CrimsonText-SemiBold.ttf", "constanb.ttf", "georgiab.ttf",
               "Georgia Bold.ttf"),
        _fonte("CrimsonText-Regular.ttf", "constan.ttf", "georgia.ttf"),
        titulo_entreletra=0.05,
    ),
    "alto_contraste": ParTipografico(
        "Alto contraste",
        # O Bodoni já viaja com o aplicativo desde a Capa Clássica.
        tema.Fonte(_empacotada("BodoniModa[opsz,wght].ttf"), "tiro"),
        _fonte("Lato-Light.ttf", "segoeuil.ttf", "segoeui.ttf", "Arial.ttf"),
        titulo_entreletra=0.08,
    ),
}


def par(nome: str) -> ParTipografico:
    try:
        return PARES[nome]
    except KeyError:
        raise ValueError(
            f"Par tipográfico desconhecido: {nome!r}. "
            f"Use um de {', '.join(sorted(PARES))}."
        ) from None


def familias_ausentes() -> tuple[str, ...]:
    """Fontes desejadas que ainda não foram empacotadas.

    Serve de diagnóstico: com a lista vazia, toda capa sai com a tipografia
    especificada; com nomes nela, esses papéis saem com a substituta do sistema.
    """
    desejadas = (
        "Montserrat-Bold.ttf", "Montserrat-Light.ttf",
        "PlayfairDisplay-BoldItalic.ttf",
        "CrimsonText-SemiBold.ttf", "CrimsonText-Regular.ttf",
        "BebasNeue-Regular.ttf", "Lato-Light.ttf",
    )
    return tuple(nome for nome in desejadas if _empacotada(nome) is None)
