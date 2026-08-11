from __future__ import annotations

from collections import deque
from hashlib import sha256
import math
import os
from pathlib import Path
import sys
import tomllib
import zipfile

from PIL import Image


ROOT = Path(__file__).parents[1]
EXPECTED_SOURCE_SHA256 = "238ab90b9ad95451b1f888b864e4b6880cddafbfebf6d9ef20f711e3f6fcbe5c"
EXPECTED_ICON_SIZES = {(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
                       (48, 48), (64, 64), (128, 128), (256, 256)}


def _external_white_pixels(image: Image.Image, tolerance: int = 8) -> set[tuple[int, int]]:
    """Reference flood-fill proving why the official open monogram needs a silhouette."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    pending = deque(((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)))
    reached = set(pending)
    while pending:
        x, y = pending.popleft()
        for candidate in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            cx, cy = candidate
            if not (0 <= cx < width and 0 <= cy < height) or candidate in reached:
                continue
            if max(abs(channel - 255) for channel in rgb.getpixel(candidate)) <= tolerance:
                reached.add(candidate)
                pending.append(candidate)
    return reached


def test_fanara_official_source_requires_convex_silhouette_to_preserve_white_monogram():
    source = ROOT / "assets" / "fanara-symbol-source.png"

    assert sha256(source.read_bytes()).hexdigest() == EXPECTED_SOURCE_SHA256
    with Image.open(source) as image:
        external = _external_white_pixels(image)
        rgb = image.convert("RGB")
        whites = {
            (index % image.width, index // image.width)
            for index, pixel in enumerate(rgb.get_flattened_data())
            if max(abs(channel - 255) for channel in pixel) <= 8
        }

    assert whites <= external, "o flood-fill literal alcança também todo o ef branco"


def test_fanara_derived_symbol_preserves_brand_color_white_monogram_and_safe_alpha():
    derived = ROOT / "assets" / "fanara-symbol.png"

    with Image.open(derived) as image:
        rgba = image.convert("RGBA")
        assert rgba.size == (1024, 1024)
        assert all(
            rgba.getpixel(point)[3] == 0
            for point in ((0, 0), (1023, 0), (0, 1023), (1023, 1023))
        )
        alpha_bounds = rgba.getchannel("A").getbbox()
        assert alpha_bounds is not None
        assert min(alpha_bounds[0], alpha_bounds[1], 1024 - alpha_bounds[2], 1024 - alpha_bounds[3]) >= 39
        pixels = list(rgba.get_flattened_data())

    opaque_colors = [(red, green, blue) for red, green, blue, alpha in pixels if alpha == 255]
    assert max(set(opaque_colors), key=opaque_colors.count) == (218, 66, 101)
    assert sum(color == (255, 255, 255) for color in opaque_colors) > 100_000


def test_fanara_external_alpha_follows_the_smooth_convex_ellipse():
    with Image.open(ROOT / "assets" / "fanara-symbol.png") as image:
        alpha = image.getchannel("A")
        left, top, right, bottom = alpha.getbbox()
        center_x = (left + right - 1) / 2
        center_y = (top + bottom - 1) / 2
        radius_x = (right - left) / 2
        radius_y = (bottom - top) / 2
        for degrees in range(0, 360, 15):
            radians = degrees * 3.141592653589793 / 180
            inner = (
                round(center_x + radius_x * 0.99 * math.cos(radians)),
                round(center_y + radius_y * 0.99 * math.sin(radians)),
            )
            outer = (
                round(center_x + radius_x * 1.01 * math.cos(radians)),
                round(center_y + radius_y * 1.01 * math.sin(radians)),
            )
            assert alpha.getpixel(inner) > 0
            if 0 <= outer[0] < alpha.width and 0 <= outer[1] < alpha.height:
                assert alpha.getpixel(outer) == 0


def test_fanara_ellipse_has_no_white_halo_away_from_the_monogram():
    with Image.open(ROOT / "assets" / "fanara-symbol.png") as image:
        rgba = image.convert("RGBA")
        left, top, right, bottom = rgba.getchannel("A").getbbox()
        center_x = (left + right - 1) / 2
        center_y = (top + bottom - 1) / 2
        radius_x = (right - left) / 2
        radius_y = (bottom - top) / 2
        for degrees in (0, 15, 30, 45, 315, 330, 345):
            radians = math.radians(degrees)
            visible = []
            for step in range(1001):
                distance = step / 1000
                point = (
                    round(center_x + radius_x * distance * math.cos(radians)),
                    round(center_y + radius_y * distance * math.sin(radians)),
                )
                pixel = rgba.getpixel(point)
                if pixel[3] >= 128:
                    visible.append(pixel)
            assert visible
            red, green, blue, _alpha = visible[-1]
            assert red >= 200 and green < 180 and blue < 200


def test_fanara_ico_contains_every_required_windows_size():
    with Image.open(ROOT / "assets" / "icone.ico") as icon:
        assert icon.format == "ICO"
        assert icon.ico.sizes() == EXPECTED_ICON_SIZES


def test_fanara_assets_are_reproducible_from_the_authorized_source(tmp_path: Path):
    from provas import recursos

    symbol = tmp_path / "fanara-symbol.png"
    icon = tmp_path / "icone.ico"
    recursos.gerar_identidade_oficial(
        ROOT / "assets" / "fanara-symbol-source.png",
        symbol,
        icon,
    )

    assert symbol.read_bytes() == (ROOT / "assets" / "fanara-symbol.png").read_bytes()
    assert icon.read_bytes() == (ROOT / "assets" / "icone.ico").read_bytes()


def test_fanara_resource_paths_support_source_and_pyinstaller(monkeypatch, tmp_path: Path):
    from provas import recursos

    assert recursos.caminho("fanara-symbol.png") == ROOT / "assets" / "fanara-symbol.png"
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert recursos.caminho("icone.ico") == tmp_path / "assets" / "icone.ico"


def test_fanara_window_uses_official_symbol_and_icon_without_deformation(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel
    from provas.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    mark = window.findChild(QLabel, "brandMark")

    assert not window.windowIcon().isNull()
    assert mark is not None and mark.pixmap() is not None and not mark.pixmap().isNull()
    assert mark.pixmap().size().width() == mark.pixmap().size().height() == 32
    window.close()
    app.processEvents()


def test_product_name_is_visible_in_window_brand_and_project_filter(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QFileDialog, QLabel
    from provas.recursos import PRODUCT_NAME
    from provas.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    captured: list[tuple[str, str]] = []

    def choose(_parent, title, _default, file_filter):
        captured.append((title, file_filter))
        return "", file_filter

    monkeypatch.setattr(QFileDialog, "getOpenFileName", choose)
    brand = window.findChild(QLabel, "brandName")
    window.open_project_button.click()

    assert window.windowTitle() == f"{PRODUCT_NAME} · Mesa de edição"
    assert brand is not None and brand.text() == PRODUCT_NAME
    assert window.open_project_button.accessibleName() == f"Abrir projeto {PRODUCT_NAME}"
    assert captured == [("Abrir projeto", f"Projeto {PRODUCT_NAME} (*.provas.json);;JSON (*.json)")]
    window.close()
    app.processEvents()


def test_product_name_is_used_for_the_qt_system_application_identity(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from provas import app as application
    from provas.recursos import PRODUCT_NAME

    class StandInWindow:
        def show(self):
            return None

    qapp = QApplication.instance() or QApplication([])
    monkeypatch.setattr(application, "MainWindow", StandInWindow)

    assert application.principal() == 0
    assert qapp.applicationName() == PRODUCT_NAME


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


def test_fanara_pyinstaller_bundles_only_tracked_identity_and_font_assets():
    from empacotar import dados_pyinstaller

    arguments = dados_pyinstaller()
    pairs = [
        arguments[index + 1].split(os.pathsep, maxsplit=1)
        for index, argument in enumerate(arguments[:-1])
        if argument == "--add-data"
    ]
    bundled = {
        (Path(source).resolve(), destination.replace("\\", "/"))
        for source, destination in pairs
    }

    assert ((ROOT / "assets" / "fanara-symbol.png").resolve(), "assets") in bundled
    assert ((ROOT / "assets" / "icone.ico").resolve(), "assets") in bundled
    assert ((ROOT / "assets" / "fonts" / "BodoniModa[opsz,wght].ttf").resolve(), "assets/fonts") in bundled
    assert ((ROOT / "assets" / "fonts" / "OFL-BodoniModa.txt").resolve(), "assets/fonts") in bundled
    assert all(source.is_relative_to(ROOT) or destination == "cv2/data" for source, destination in bundled)


def test_inspecao_do_zip_exige_ativos_e_rejeita_dados_do_usuario(tmp_path: Path):
    from empacotar import inspecionar_pacote
    from provas.recursos import PRODUCT_NAME

    pacote = tmp_path / f"{PRODUCT_NAME}-Windows.zip"
    with zipfile.ZipFile(pacote, "w") as archive:
        for name in (
            f"{PRODUCT_NAME}/{PRODUCT_NAME}.exe",
            f"{PRODUCT_NAME}/BUILD-MANIFEST.json",
            f"{PRODUCT_NAME}/LEIA-ME.txt",
            f"{PRODUCT_NAME}/_internal/provas/ui/theme.qss",
            f"{PRODUCT_NAME}/_internal/PySide6/plugins/platforms/qwindows.dll",
            f"{PRODUCT_NAME}/_internal/cv2/data/haarcascade_frontalface_default.xml",
        ):
            archive.writestr(name, b"ok")
        for asset in (
            ROOT / "assets" / "fanara-symbol.png",
            ROOT / "assets" / "icone.ico",
            ROOT / "assets" / "fonts" / "BodoniModa[opsz,wght].ttf",
            ROOT / "assets" / "fonts" / "OFL-BodoniModa.txt",
        ):
            archive.writestr(f"{PRODUCT_NAME}/_internal/{asset.relative_to(ROOT).as_posix()}", asset.read_bytes())

    assert inspecionar_pacote(pacote) == ()

    with zipfile.ZipFile(pacote, "a") as archive:
        archive.writestr(f"{PRODUCT_NAME}/config.json", b"privado")
        archive.writestr(f"{PRODUCT_NAME}/sessao.jpg", b"fotografia")
        archive.writestr(f"{PRODUCT_NAME}/marca-cliente.png", b"logotipo")
        archive.writestr(f"{PRODUCT_NAME}/marca-alternativa.bmp", b"logotipo")
        archive.writestr(f"{PRODUCT_NAME}/marca-animada.gif", b"logotipo")
        archive.writestr(f"{PRODUCT_NAME}/marca-web.webp", b"logotipo")
        archive.writestr(f"{PRODUCT_NAME}/foto-camera.NEF", b"raw")
        archive.writestr(f"{PRODUCT_NAME}/cliente.provas.json", b"projeto")
    problemas = inspecionar_pacote(pacote)
    assert any("config.json" in problema for problema in problemas)
    assert any("sessao.jpg" in problema for problema in problemas)
    assert any("marca-cliente.png" in problema for problema in problemas)
    assert any("marca-alternativa.bmp" in problema for problema in problemas)
    assert any("marca-animada.gif" in problema for problema in problemas)
    assert any("marca-web.webp" in problema for problema in problemas)
    assert any("foto-camera.nef" in problema for problema in problemas)
    assert any("cliente.provas.json" in problema for problema in problemas)


def test_fanara_zip_rejects_official_filename_with_untracked_content(tmp_path: Path):
    from empacotar import inspecionar_pacote
    from provas.recursos import PRODUCT_NAME

    pacote = tmp_path / f"{PRODUCT_NAME}-Windows.zip"
    with zipfile.ZipFile(pacote, "w") as archive:
        archive.writestr(f"{PRODUCT_NAME}/_internal/assets/fanara-symbol.png", b"imagem substituida")

    problemas = inspecionar_pacote(pacote)
    assert any("hash" in problema and "fanara-symbol.png" in problema for problema in problemas)


def test_fanara_verifier_confirms_tracked_identity_font_and_license(capsys):
    import verificar

    assert verificar.diagnosticar_recursos() == 0
    output = capsys.readouterr().out
    assert "fanara-symbol.png" in output
    assert "icone.ico" in output
    assert "BodoniModa[opsz,wght].ttf" in output
    assert "OFL-BodoniModa.txt" in output


def test_packaging_removes_user_configuration_and_logo_but_keeps_application_files(tmp_path: Path):
    from empacotar import remover_dados_usuario
    from provas.recursos import PRODUCT_NAME

    (tmp_path / "config.json").write_text("dados pessoais", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"marca do usuario")
    (tmp_path / f"{PRODUCT_NAME}.exe").write_bytes(b"executavel")
    (tmp_path / "provas" / "ui").mkdir(parents=True)
    theme = tmp_path / "provas" / "ui" / "theme.qss"
    theme.write_text("QWidget {}", encoding="utf-8")

    remover_dados_usuario(str(tmp_path))

    assert not (tmp_path / "config.json").exists()
    assert not (tmp_path / "logo.png").exists()
    assert (tmp_path / f"{PRODUCT_NAME}.exe").exists()
    assert theme.exists()


def test_package_name_centralizes_artifacts_manifest_and_public_text():
    from empacotar import LEIAME_WINDOWS, NOME
    from provas.recursos import PRODUCT_NAME

    source = (ROOT / "empacotar.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    obsolete_executable_path = "Fotolivro" + "/Fotolivro.exe"
    obsolete_package_path = "dist/Fotolivro" + "-Windows.zip"

    assert NOME == PRODUCT_NAME
    assert f'"{PRODUCT_NAME}.exe"' in LEIAME_WINDOWS
    assert f"dist/{PRODUCT_NAME}-Windows.zip" in readme
    assert obsolete_executable_path not in source
    assert obsolete_package_path not in source
    assert obsolete_executable_path not in readme
    assert obsolete_package_path not in readme


def test_windows_packager_recuses_other_platforms(monkeypatch, capsys):
    import empacotar

    monkeypatch.setattr(empacotar.sys, "platform", "darwin")

    assert empacotar.main() == 1
    assert "Windows" in capsys.readouterr().out
