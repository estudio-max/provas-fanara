"""Gera o pacote Windows do Fotolivro editorial.

    python empacotar.py

Produz `dist/Fotolivro/` e `dist/Fotolivro-Windows.zip`. Este empacotador é
deliberadamente Windows-only: o PyInstaller não faz compilação cruzada.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.abspath(__file__))
NOME = "Fotolivro"
ENTRADA = os.path.join(RAIZ, "empacotar_entrada.py")
MANIFESTO = "BUILD-MANIFEST.json"

LEIAME_WINDOWS = """FOTOLIVRO — PDF editorial a partir da pasta do ensaio

PRIMEIRO USO
1. Extraia a pasta inteira e abra "Fotolivro.exe". Não separe a pasta
   "_internal", pois ela contém as bibliotecas do aplicativo.
2. Clique em "Escolher pasta" e depois em "Analisar fotografias".
3. Escolha "Prova para seleção" (marca d'água e códigos) ou "Fotolivro limpo"
   (sem os dois), revise a prévia e, se desejar, use "Trocar fotos da capa".
4. Clique em "Exportar PDF". "Salvar projeto" grava apenas o plano e os
   caminhos das fotos; as fotografias continuam na pasta original.

O QUE ELE LÊ
JPG/JPEG e RAW usuais (.NEF, .CR2, .ARW, .DNG, .ORF e .RW2). Para RAW, usa a
prévia JPEG integrada pela câmera; não revela RAW nem aplica ajustes de cor ou
lente. RAW e JPG de mesmo nome representam uma única foto.

PRIVACIDADE
O pacote não contém suas preferências locais nem logotipo. Projetos .provas.json
não guardam cópias das fotografias.
A detecção de rosto é executada localmente; nenhuma fotografia é enviada pela
internet.

AVISO DO WINDOWS
Por ser um programa sem assinatura digital paga, pode aparecer "O Windows
protegeu o computador". Clique em "Mais informações" e depois em "Executar
assim mesmo".
"""


def dados_pyinstaller() -> list[str]:
    """Bundle UI and the minimal local face-detector runtime."""
    import cv2
    from PySide6 import __file__ as pyside_package

    theme = os.path.join(RAIZ, "provas", "ui", "theme.qss")
    platform_plugin = os.path.join(
        os.path.dirname(pyside_package), "plugins", "platforms", "qwindows.dll",
    )
    cascade = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
    if not os.path.isfile(cascade):
        raise FileNotFoundError(f"Cascade Haar local não encontrado: {cascade}")
    return [
        "--add-data", f"{theme}{os.pathsep}provas/ui",
        "--add-binary", f"{platform_plugin}{os.pathsep}PySide6/plugins/platforms",
        "--add-data", f"{cascade}{os.pathsep}cv2/data",
        "--hidden-import", "cv2",
        "--hidden-import", "numpy",
        # O detector usa apenas cvtColor/CascadeClassifier. O código Python
        # opcional de Graph API é carregado dinamicamente e pode ser omitido.
        "--exclude-module", "cv2.gapi",
    ]


def inspecionar_pacote(pacote: str | Path) -> tuple[str, ...]:
    """Return actionable packaging contract violations without extracting data."""
    obrigatorios = (
        "Fotolivro/Fotolivro.exe",
        "Fotolivro/BUILD-MANIFEST.json",
        "Fotolivro/LEIA-ME.txt",
    )
    problemas: list[str] = []
    with zipfile.ZipFile(pacote) as archive:
        nomes = tuple(name.replace("\\", "/") for name in archive.namelist())
    minusculos = tuple(name.lower() for name in nomes)
    for obrigatorio in obrigatorios:
        if obrigatorio.lower() not in minusculos:
            problemas.append(f"arquivo obrigatório ausente: {obrigatorio}")
    ativos = {
        "QSS": lambda name: name.endswith("/provas/ui/theme.qss"),
        "qwindows": lambda name: name.endswith("/pyside6/plugins/platforms/qwindows.dll"),
        "cascade Haar": lambda name: name.endswith("/cv2/data/haarcascade_frontalface_default.xml"),
    }
    for rotulo, presente in ativos.items():
        if not any(presente(name) for name in minusculos):
            problemas.append(f"ativo obrigatório ausente: {rotulo}")
    proibidos = {"config.json", "logo.png"}
    extensoes_fotograficas = {".jpg", ".jpeg", ".nef", ".cr2", ".arw", ".dng", ".orf", ".rw2"}
    for name in minusculos:
        if Path(name).name in proibidos:
            problemas.append(f"dado de usuário incluído: {name}")
        elif Path(name).suffix in extensoes_fotograficas:
            problemas.append(f"fotografia incluída no pacote: {name}")
    return tuple(problemas)


def remover_dados_usuario(pasta: str) -> None:
    """Never ship the local preferences or a photographer's watermark asset."""
    for nome in ("config.json", "logo.png"):
        caminho = os.path.join(pasta, nome)
        if os.path.isfile(caminho):
            os.unlink(caminho)


def gerar_icone() -> str | None:
    """Create the neutral Windows icon embedded in the executable."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    caminho = os.path.join(RAIZ, "assets", "icone.ico")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    lado, escala = 512, 2
    tela = Image.new("RGBA", (lado * escala, lado * escala), (22, 22, 26, 255))
    desenho = ImageDraw.Draw(tela)
    meio, raio = lado * escala / 2, lado * escala * 0.33
    desenho.polygon([(meio, meio - raio), (meio + raio, meio),
                     (meio, meio + raio), (meio - raio, meio)], fill=(236, 237, 240, 255))
    interno = raio * 0.45
    desenho.polygon([(meio, meio - interno), (meio + interno, meio),
                     (meio, meio + interno), (meio - interno, meio)], fill=(216, 64, 96, 255))
    tela.resize((lado, lado), Image.Resampling.LANCZOS).save(
        caminho, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return caminho


def compactar(alvo: str, destino_zip: str) -> str:
    return shutil.make_archive(os.path.splitext(destino_zip)[0], "zip", os.path.dirname(alvo), os.path.basename(alvo))


def _fontes_do_pacote() -> tuple[Path, ...]:
    root = Path(RAIZ)
    fixed = tuple(
        root / name for name in (
            "pyproject.toml", "provas_cli.py", "Provas.pyw", "verificar.py", "empacotar.py",
        )
    )
    package = tuple(path for path in (root / "provas").rglob("*") if path.suffix in {".py", ".qss"})
    return tuple(sorted((*fixed, *package), key=lambda path: path.relative_to(root).as_posix()))


def fingerprint_fontes() -> str:
    """Hash every source file that can affect the frozen executable."""
    digest = hashlib.sha256()
    root = Path(RAIZ)
    for path in _fontes_do_pacote():
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def commit_atual() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=RAIZ, text=True, capture_output=True, check=True,
    )
    return completed.stdout.strip()


def escrever_manifesto(alvo: str) -> None:
    executable = Path(alvo, f"{NOME}.exe")
    Path(alvo, MANIFESTO).write_text(
        json.dumps(
            {
                "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "git_commit": commit_atual(),
                "source_sha256": fingerprint_fontes(),
            },
            ensure_ascii=False, indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if sys.platform != "win32":
        print("Este empacotador gera somente o pacote Windows; execute-o no Windows.")
        return 1
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller não está instalado. Rode: python -m pip install pyinstaller")
        return 1

    with open(ENTRADA, "w", encoding="utf-8") as arquivo:
        arquivo.write(
            "import sys\n\n"
            "if len(sys.argv) > 1:\n"
            "    from provas_cli import main\n"
            "    raise SystemExit(main(sys.argv[1:]))\n\n"
            "from provas.app import principal\n\n"
            "raise SystemExit(principal())\n"
        )

    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", NOME,
        "--distpath", os.path.join(RAIZ, "dist"), "--workpath", os.path.join(RAIZ, "build"),
        "--specpath", os.path.join(RAIZ, "build"), "--paths", RAIZ,
        "--exclude-module", "matplotlib", "--exclude-module", "scipy",
        "--exclude-module", "pandas", "--exclude-module", "PIL.ImageQt", "--exclude-module", "PyQt5",
        "--exclude-module", "PySide2", "--exclude-module", "test",
        *dados_pyinstaller(),
    ]
    icone = gerar_icone()
    if icone:
        comando.extend(("--icon", icone))
    comando.append(ENTRADA)

    print("Empacotando…")
    try:
        resultado = subprocess.run(comando, cwd=RAIZ)
    finally:
        if os.path.exists(ENTRADA):
            os.remove(ENTRADA)
    if resultado.returncode != 0:
        return resultado.returncode

    alvo = os.path.join(RAIZ, "dist", NOME)
    remover_dados_usuario(alvo)
    escrever_manifesto(alvo)
    leiame = os.path.join(alvo, "LEIA-ME.txt")
    with open(leiame, "w", encoding="utf-8") as arquivo:
        arquivo.write(LEIAME_WINDOWS)
    pacote = compactar(alvo, os.path.join(RAIZ, "dist", f"{NOME}-Windows.zip"))
    problemas = inspecionar_pacote(pacote)
    if problemas:
        print("\nO pacote falhou na inspeção:")
        for problema in problemas:
            print(f"  - {problema}")
        return 1
    print(f"\nAplicativo: {alvo}")
    print(f"Enviar:     {pacote}  ({os.path.getsize(pacote) / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
