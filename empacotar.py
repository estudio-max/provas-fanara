"""Gera o pacote Windows do Fotolivro editorial.

    python empacotar.py

Produz `dist/Fotolivro/` e `dist/Fotolivro-Windows.zip`. Este empacotador é
deliberadamente Windows-only: o PyInstaller não faz compilação cruzada.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
NOME = "Fotolivro"
ENTRADA = os.path.join(RAIZ, "empacotar_entrada.py")

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

AVISO DO WINDOWS
Por ser um programa sem assinatura digital paga, pode aparecer "O Windows
protegeu o computador". Clique em "Mais informações" e depois em "Executar
assim mesmo".
"""


def dados_pyinstaller() -> list[str]:
    """Bundle the application stylesheet and the required Windows Qt plugin."""
    from PySide6 import __file__ as pyside_package

    theme = os.path.join(RAIZ, "provas", "ui", "theme.qss")
    platform_plugin = os.path.join(
        os.path.dirname(pyside_package), "plugins", "platforms", "qwindows.dll",
    )
    return [
        "--add-data", f"{theme}{os.pathsep}provas/ui",
        "--add-binary", f"{platform_plugin}{os.pathsep}PySide6/plugins/platforms",
    ]


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
        arquivo.write("from provas.app import principal\n\nprincipal()\n")

    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", NOME,
        "--distpath", os.path.join(RAIZ, "dist"), "--workpath", os.path.join(RAIZ, "build"),
        "--specpath", os.path.join(RAIZ, "build"), "--paths", RAIZ,
        "--exclude-module", "numpy", "--exclude-module", "matplotlib", "--exclude-module", "scipy",
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
    leiame = os.path.join(alvo, "LEIA-ME.txt")
    with open(leiame, "w", encoding="utf-8") as arquivo:
        arquivo.write(LEIAME_WINDOWS)
    pacote = compactar(alvo, os.path.join(RAIZ, "dist", f"{NOME}-Windows.zip"))
    print(f"\nAplicativo: {alvo}")
    print(f"Enviar:     {pacote}  ({os.path.getsize(pacote) / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
