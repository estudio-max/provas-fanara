"""Gera o pacote Windows do Fanara - Fotolivro.

    python empacotar.py

Produz `dist/Fanara - Fotolivro/` e `dist/Fanara - Fotolivro-Windows.zip`. Este empacotador é
deliberadamente Windows-only: o PyInstaller não faz compilação cruzada.
"""
from __future__ import annotations

import hashlib
import json
import glob
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from provas.recursos import PRODUCT_NAME

RAIZ = os.path.dirname(os.path.abspath(__file__))
NOME = PRODUCT_NAME
ENTRADA = os.path.join(RAIZ, "empacotar_entrada.py")
MANIFESTO = "BUILD-MANIFEST.json"
#: Tudo que mora em assets/, pelo caminho relativo. O pacote não pode levar
#: imagem nenhuma além destas: é o que impede uma fotografia ou o logotipo de
#: um cliente sair junto na distribuição.
OFFICIAL_ASSETS = {
    caminho.relative_to(Path(RAIZ, "assets")).as_posix():
        hashlib.sha256(caminho.read_bytes()).hexdigest()
    for caminho in sorted(Path(RAIZ, "assets").rglob("*"))
    if caminho.is_file()
}

LEIAME_WINDOWS = f"""{PRODUCT_NAME} — PDF editorial a partir da pasta do ensaio

PRIMEIRO USO
1. Extraia a pasta inteira e abra "{PRODUCT_NAME}.exe". Não separe a pasta
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
    official_data = (
        (os.path.join(RAIZ, "assets", "fanara-symbol.png"), "assets"),
        (os.path.join(RAIZ, "assets", "icone.ico"), "assets"),
        *(
            (caminho, "assets/fonts")
            for caminho in sorted(glob.glob(os.path.join(RAIZ, "assets", "fonts", "*")))
        ),
        *(
            (caminho, "assets/passo-a-passo")
            for caminho in sorted(glob.glob(os.path.join(RAIZ, "assets", "passo-a-passo", "*.jpg")))
        ),
    )
    if not os.path.isfile(cascade):
        raise FileNotFoundError(f"Cascade Haar local não encontrado: {cascade}")
    arguments = [
        "--add-data", f"{theme}{os.pathsep}provas/ui",
        "--add-binary", f"{platform_plugin}{os.pathsep}PySide6/plugins/platforms",
        "--add-data", f"{cascade}{os.pathsep}cv2/data",
        "--hidden-import", "cv2",
        "--hidden-import", "numpy",
        # O detector usa apenas cvtColor/CascadeClassifier. O código Python
        # opcional de Graph API é carregado dinamicamente e pode ser omitido.
        "--exclude-module", "cv2.gapi",
    ]
    for source, destination in official_data:
        arguments.extend(("--add-data", f"{source}{os.pathsep}{destination}"))
    return arguments


def inspecionar_pacote(pacote: str | Path) -> tuple[str, ...]:
    """Return actionable packaging contract violations without extracting data."""
    from PIL import Image

    obrigatorios = (
        f"{NOME}/{NOME}.exe",
        f"{NOME}/BUILD-MANIFEST.json",
        f"{NOME}/LEIA-ME.txt",
    )
    prefixo_interno = f"{NOME.casefold()}/_internal/"
    problemas: list[str] = []
    with zipfile.ZipFile(pacote) as archive:
        nomes = tuple(name.replace("\\", "/") for name in archive.namelist())
        hashes = {
            name.lower(): hashlib.sha256(archive.read(original)).hexdigest()
            for name, original in zip(nomes, archive.namelist())
            if name.lower().startswith(f"{prefixo_interno}assets/")
        }
    minusculos = tuple(name.lower() for name in nomes)
    for obrigatorio in obrigatorios:
        if obrigatorio.lower() not in minusculos:
            problemas.append(f"arquivo obrigatório ausente: {obrigatorio}")
    ativos = {
        "QSS": lambda name: name.endswith("/provas/ui/theme.qss"),
        "qwindows": lambda name: name.endswith("/pyside6/plugins/platforms/qwindows.dll"),
        "cascade Haar": lambda name: name.endswith("/cv2/data/haarcascade_frontalface_default.xml"),
        "símbolo Fanara": lambda name: name == f"{prefixo_interno}assets/fanara-symbol.png",
        "ícone Fanara": lambda name: name == f"{prefixo_interno}assets/icone.ico",
    }
    # Fonte faltando não quebra nada: a capa sai com a substituta do sistema, com
    # outra métrica e outro desenho. Só se percebe olhando o PDF, então é aqui.
    for fonte in sorted(glob.glob(os.path.join(RAIZ, "assets", "fonts", "*"))):
        interno = f"{prefixo_interno}assets/fonts/{os.path.basename(fonte).lower()}"
        ativos[os.path.basename(fonte)] = (
            lambda name, alvo=interno: name == alvo
        )
    for rotulo, presente in ativos.items():
        if not any(presente(name) for name in minusculos):
            problemas.append(f"ativo obrigatório ausente: {rotulo}")
    proibidos = {"config.json", "logo.png"}
    oficiais = {nome.lower(): digest for nome, digest in OFFICIAL_ASSETS.items()}
    Image.init()
    extensoes_de_imagem = set(Image.registered_extensions()) | {
        ".nef", ".cr2", ".arw", ".dng", ".orf", ".rw2",
    }
    for name in minusculos:
        if name.endswith("/"):        # entrada de diretório, não carrega conteúdo
            continue
        if Path(name).name in proibidos:
            problemas.append(f"dado de usuário incluído: {name}")
        elif name.endswith(".provas.json"):
            problemas.append(f"projeto de usuário incluído: {name}")
        elif name.startswith(f"{prefixo_interno}assets/"):
            relativo = name[len(f"{prefixo_interno}assets/"):]
            esperado = oficiais.get(relativo)
            if esperado is None:
                problemas.append(f"ativo não oficial no pacote: {name}")
            elif hashes.get(name) != esperado:
                problemas.append(f"ativo oficial com hash inválido: {name}")
        elif Path(name).suffix in extensoes_de_imagem:
            problemas.append(f"fotografia ou logotipo incluído no pacote: {name}")
    return tuple(problemas)


def remover_dados_usuario(pasta: str) -> None:
    """Never ship the local preferences or a photographer's watermark asset."""
    for nome in ("config.json", "logo.png"):
        caminho = os.path.join(pasta, nome)
        if os.path.isfile(caminho):
            os.unlink(caminho)


def gerar_icone() -> str | None:
    """Regenerate the tracked official identity before freezing the executable."""
    try:
        from provas.recursos import gerar_identidade_oficial
    except ImportError:
        return None
    source = Path(RAIZ, "assets", "fanara-symbol-source.png")
    symbol = Path(RAIZ, "assets", "fanara-symbol.png")
    caminho = os.path.join(RAIZ, "assets", "icone.ico")
    gerar_identidade_oficial(source, symbol, Path(caminho))
    return caminho


def compactar(alvo: str, destino_zip: str) -> str:
    return shutil.make_archive(os.path.splitext(destino_zip)[0], "zip", os.path.dirname(alvo), os.path.basename(alvo))


def _fontes_do_pacote() -> tuple[Path, ...]:
    root = Path(RAIZ)
    fixed = tuple(
        root / name for name in (
            "pyproject.toml", "provas_cli.py", "Provas.pyw", "verificar.py", "empacotar.py",
            "assets/fanara-symbol-source.png", "assets/fanara-symbol.png", "assets/icone.ico",
        )
    )
    fontes = tuple(sorted(Path(RAIZ, "assets", "fonts").iterdir()))
    package = tuple(path for path in (root / "provas").rglob("*") if path.suffix in {".py", ".qss"})
    return tuple(sorted((*fixed, *fontes, *package),
                        key=lambda path: path.relative_to(root).as_posix()))


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
