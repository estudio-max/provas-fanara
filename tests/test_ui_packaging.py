from __future__ import annotations

import os
from pathlib import Path
import tomllib
import zipfile


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
    assert arguments[2] == "--add-binary"
    plugin_source, plugin_destination = arguments[3].split(os.pathsep, maxsplit=1)
    assert Path(plugin_source).name == "qwindows.dll"
    assert plugin_destination.replace("\\", "/") == "PySide6/plugins/platforms"


def test_pyinstaller_inclui_opencv_numpy_e_cascade_local_sem_modulos_desnecessarios():
    from empacotar import dados_pyinstaller

    arguments = dados_pyinstaller()
    joined = " ".join(arguments).replace("\\", "/")

    assert "--hidden-import cv2" in joined
    assert "--hidden-import numpy" in joined
    assert "haarcascade_frontalface_default.xml" in joined
    assert "cv2/data" in joined
    assert "--exclude-module cv2.gapi" in joined


def test_inspecao_do_zip_exige_ativos_e_rejeita_dados_do_usuario(tmp_path: Path):
    from empacotar import inspecionar_pacote

    pacote = tmp_path / "Fotolivro-Windows.zip"
    with zipfile.ZipFile(pacote, "w") as archive:
        for name in (
            "Fotolivro/Fotolivro.exe",
            "Fotolivro/BUILD-MANIFEST.json",
            "Fotolivro/LEIA-ME.txt",
            "Fotolivro/_internal/provas/ui/theme.qss",
            "Fotolivro/_internal/PySide6/plugins/platforms/qwindows.dll",
            "Fotolivro/_internal/cv2/data/haarcascade_frontalface_default.xml",
        ):
            archive.writestr(name, b"ok")

    assert inspecionar_pacote(pacote) == ()

    with zipfile.ZipFile(pacote, "a") as archive:
        archive.writestr("Fotolivro/config.json", b"privado")
        archive.writestr("Fotolivro/sessao.jpg", b"fotografia")
    problemas = inspecionar_pacote(pacote)
    assert any("config.json" in problema for problema in problemas)
    assert any("sessao.jpg" in problema for problema in problemas)


def test_packaging_removes_user_configuration_and_logo_but_keeps_application_files(tmp_path: Path):
    from empacotar import remover_dados_usuario

    (tmp_path / "config.json").write_text("dados pessoais", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"marca do usuario")
    (tmp_path / "Fotolivro.exe").write_bytes(b"executavel")
    (tmp_path / "provas" / "ui").mkdir(parents=True)
    theme = tmp_path / "provas" / "ui" / "theme.qss"
    theme.write_text("QWidget {}", encoding="utf-8")

    remover_dados_usuario(str(tmp_path))

    assert not (tmp_path / "config.json").exists()
    assert not (tmp_path / "logo.png").exists()
    assert (tmp_path / "Fotolivro.exe").exists()
    assert theme.exists()


def test_windows_packager_recuses_other_platforms(monkeypatch, capsys):
    import empacotar

    monkeypatch.setattr(empacotar.sys, "platform", "darwin")

    assert empacotar.main() == 1
    assert "Windows" in capsys.readouterr().out
