"""Preferências do usuário, guardadas pelo Windows.

O `QSettings` monta o caminho no registro a partir da organização e do nome do
produto — `HKCU\\Software\\Estúdio Fanara\\Fanara - Fotolivro`. Mudar qualquer um
dos dois depois de publicado faz o usuário perder o que já escolheu, então os
dois vêm de `recursos`, que é a fonte única.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

from .recursos import ORGANIZATION_NAME, PRODUCT_NAME

_BOAS_VINDAS = "boas_vindas/mostrar"


def _registro() -> QSettings:
    return QSettings(ORGANIZATION_NAME, PRODUCT_NAME)


def mostrar_boas_vindas() -> bool:
    """Se a tela de abertura deve aparecer. Verdadeiro até o usuário dispensá-la."""
    return bool(_registro().value(_BOAS_VINDAS, True, type=bool))


def definir_mostrar_boas_vindas(mostrar: bool) -> None:
    _registro().setValue(_BOAS_VINDAS, bool(mostrar))
