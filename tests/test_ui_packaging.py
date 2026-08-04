from __future__ import annotations

import os
from pathlib import Path
import tomllib


def test_theme_qss_is_declared_for_wheels_and_pyinstaller():
    root = Path(__file__).parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert "theme.qss" in config["tool"]["setuptools"]["package-data"]["provas.ui"]

    from empacotar import dados_pyinstaller

    arguments = dados_pyinstaller()
    assert arguments[:1] == ["--add-data"]
    source, destination = arguments[1].split(os.pathsep, maxsplit=1)
    assert Path(source).resolve() == (root / "provas" / "ui" / "theme.qss").resolve()
    assert destination.replace("\\", "/") == "provas/ui"
