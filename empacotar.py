"""Gera o aplicativo do Provas para distribuir.

    python empacotar.py

No Windows produz `dist/Provas/` (pasta) e `dist/Provas-Windows.zip`.
No macOS produz `dist/Provas.app` e `dist/Provas-macOS.zip`.

O PyInstaller NÃO faz compilação cruzada: para ter a versão de Mac é preciso
rodar este script num Mac, e o pacote sai para a arquitetura daquela máquina
(Apple Silicon ou Intel).

O modo pasta (em vez de arquivo único) no Windows foi escolhido de propósito:
abre bem mais rápido, porque não descompacta ~80 MB a cada execução, e dispara
muito menos alarme falso de antivírus.

O logotipo NÃO vai embutido: quem receber aponta o próprio na janela.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
NOME = "Provas"
IDENTIFICADOR = "com.provas.selecao"
ENTRADA = os.path.join(RAIZ, "empacotar_entrada.py")
MAC = sys.platform == "darwin"

LEIAME_COMUM = """PROVAS — monta o PDF de seleção de fotos a partir da pasta do ensaio

PRIMEIRO USO
Preencha "Nome do estúdio", "Site" e escolha o seu logotipo (um PNG com fundo
transparente) no campo Logotipo. Isso fica salvo para as próximas vezes.
Depois: escolha a pasta do ensaio, clique em "Amostra (12 fotos)" para conferir
e então em "Gerar PDF".

O QUE ELE LÊ
JPG, e também RAW (.NEF, .CR2, .ARW, .DNG, .ORF, .RW2 e outros). Em pastas só
com RAW ele usa a pré-visualização em tamanho cheio que a câmera grava dentro do
arquivo, por isso é rápido. Havendo RAW e JPG de mesmo nome, é a mesma foto.

DOIS MODOS
- Prova: com marca d'água e com o código do arquivo sob cada foto.
- Álbum: desligue "Aplicar" (marca d'água) e "Códigos sob as fotos". Sem a
  legenda, a foto sai maior.
"""

LEIAME_WINDOWS = LEIAME_COMUM + """
COMO ABRIR
Extraia esta pasta inteira e abra "Provas.exe". Não separe os arquivos: o
programa depende da pasta "_internal" que está ao lado.

AVISO DO WINDOWS
Por ser um programa sem assinatura digital paga, pode aparecer "O Windows
protegeu o computador". Clique em "Mais informações" e depois em "Executar
assim mesmo".
"""

LEIAME_MAC = LEIAME_COMUM + """
COMO ABRIR
Arraste "Provas.app" para a pasta Aplicativos (ou deixe onde preferir).

AVISO DO macOS — IMPORTANTE
Na primeira vez o macOS vai recusar, dizendo que o desenvolvedor não pode ser
verificado. Isso acontece com qualquer programa sem assinatura paga da Apple.
Para liberar: clique com o botão direito (ou Control+clique) no Provas.app e
escolha "Abrir", e então confirme "Abrir" na caixa que aparecer. Só é preciso
fazer isso uma vez.

Se mesmo assim disser que o app "está danificado", abra o Terminal e rode:
    xattr -dr com.apple.quarantine "/caminho/para/Provas.app"

Requer macOS Monterey (12) ou mais novo.
"""


def dados_pyinstaller() -> list[str]:
    """Bundle the stylesheet at the same package-relative path used at runtime."""
    source = os.path.join(RAIZ, "provas", "ui", "theme.qss")
    return ["--add-data", f"{source}{os.pathsep}provas/ui"]


def gerar_icone() -> str | None:
    """Ícone neutro: um losango claro sobre fundo grafite, sem marca de estúdio.

    No macOS o PyInstaller converte o PNG para .icns; no Windows usa o .ico.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    pasta = os.path.join(RAIZ, "assets")
    os.makedirs(pasta, exist_ok=True)

    lado, escala = 512, 2
    tela = Image.new("RGBA", (lado * escala, lado * escala), (22, 22, 26, 255))
    desenho = ImageDraw.Draw(tela)
    meio = lado * escala / 2
    raio = lado * escala * 0.33
    desenho.polygon([(meio, meio - raio), (meio + raio, meio),
                     (meio, meio + raio), (meio - raio, meio)], fill=(236, 237, 240, 255))
    interno = raio * 0.45
    desenho.polygon([(meio, meio - interno), (meio + interno, meio),
                     (meio, meio + interno), (meio - interno, meio)], fill=(216, 64, 96, 255))
    tela = tela.resize((lado, lado), Image.Resampling.LANCZOS)

    if MAC:
        caminho = os.path.join(pasta, "icone.png")
        tela.save(caminho)
        return caminho
    caminho = os.path.join(pasta, "icone.ico")
    tela.resize((256, 256), Image.Resampling.LANCZOS).save(
        caminho, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return caminho


def compactar(alvo: str, destino_zip: str) -> str:
    """Compacta preservando permissões — no macOS isso importa para o .app."""
    if MAC and shutil.which("ditto"):
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        alvo, destino_zip], check=True)
        return destino_zip
    return shutil.make_archive(os.path.splitext(destino_zip)[0], "zip",
                               os.path.dirname(alvo), os.path.basename(alvo))


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller não está instalado. Rode:  python -m pip install pyinstaller")
        return 1

    with open(ENTRADA, "w", encoding="utf-8") as arquivo:
        arquivo.write("from provas.app import principal\n\nprincipal()\n")

    icone = gerar_icone()
    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--windowed", "--name", NOME,
        "--distpath", os.path.join(RAIZ, "dist"),
        "--workpath", os.path.join(RAIZ, "build"),
        "--specpath", os.path.join(RAIZ, "build"),
        "--paths", RAIZ,
        # o app usa só tkinter, Pillow e PyMuPDF; o resto é peso morto no pacote
        "--exclude-module", "numpy", "--exclude-module", "matplotlib",
        "--exclude-module", "scipy", "--exclude-module", "pandas",
        "--exclude-module", "PIL.ImageQt", "--exclude-module", "PyQt5",
        "--exclude-module", "PySide2", "--exclude-module", "test",
    ]
    comando += dados_pyinstaller()
    if icone:
        comando += ["--icon", icone]
    if MAC:
        comando += ["--osx-bundle-identifier", IDENTIFICADOR]
    comando.append(ENTRADA)

    print("Empacotando…")
    resultado = subprocess.run(comando, cwd=RAIZ)
    os.remove(ENTRADA)
    if resultado.returncode != 0:
        return resultado.returncode

    if MAC:
        alvo = os.path.join(RAIZ, "dist", f"{NOME}.app")
        leiame = os.path.join(RAIZ, "dist", "LEIA-ME.txt")
        texto = LEIAME_MAC
        zipe = os.path.join(RAIZ, "dist", f"{NOME}-macOS.zip")
    else:
        alvo = os.path.join(RAIZ, "dist", NOME)
        leiame = os.path.join(alvo, "LEIA-ME.txt")
        texto = LEIAME_WINDOWS
        zipe = os.path.join(RAIZ, "dist", f"{NOME}-Windows.zip")

    with open(leiame, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)

    pacote = compactar(alvo, zipe)
    print(f"\nAplicativo: {alvo}")
    print(f"Enviar:     {pacote}  ({os.path.getsize(pacote) / 1e6:.0f} MB)")
    if MAC:
        print("Lembre o destinatário de abrir a primeira vez com botão direito → Abrir.")
        print(f"Mande junto o {leiame}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
