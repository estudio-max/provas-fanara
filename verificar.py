"""Diagnóstico do ambiente e do pipeline editorial.

    python verificar.py
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import platform
import sys
import tempfile

from provas.recursos import PRODUCT_NAME

try:
    from packaging.version import InvalidVersion, Version
except ImportError:
    InvalidVersion = ValueError
    Version = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OK, FALHA, AVISO = "  ok ", "FALHA", "aviso"
DEPENDENCIAS = (
    ("PIL", "Pillow", "10.0"), ("pymupdf", "PyMuPDF", "1.24"),
    ("PySide6", "PySide6", "6.7"), ("packaging", "packaging", "23.0"),
    ("numpy", "NumPy", "1.26"), ("cv2", "OpenCV", "4.10", "5"),
)
RECURSOS_OFICIAIS = {
    "fanara-symbol.png": "a6771c2caa80614f1223e4a158c114dc4cf573005df774539494492b5eba7ae4",
    "icone.ico": "5931ba87d2947ba6362a8c1e08a5b84c64ea00274040221ad354c6f3944dd2a2",
    "fonts/BebasNeue-Regular.ttf": "08e4623805102d819f58601e46e345648846075e363b2ceb23313c2d1c83ec73",
    "fonts/BodoniModa[opsz,wght].ttf": "550f5e34ee0a828d7941b1fe9bc58b34e5260d3f33a61532e6d0a0114e79a5cf",
    "fonts/CrimsonText-Regular.ttf": "48e6c5d5ad1d01599d374ecb817e15890d1feb3b8a3a88e527d44c90389e1f06",
    "fonts/CrimsonText-SemiBold.ttf": "802e84000740fec2a9fbe0ae09b6b6811bd86a78a0173b15d44450a1530e9410",
    "fonts/Lato-Light.ttf": "cf2a774503baf418d584f49967bd160e1e03f087c13b25602f28024ec7788f08",
    "fonts/Montserrat-Bold.ttf": "5a491022018fd3965df4c071a581b055971e5be605b6df79d7ab03437a10234e",
    "fonts/Montserrat-Light.ttf": "a30a5d096ee32d9e4d7952daee4807e726b5201bea5d9951f0fb5a8619388555",
    "fonts/OFL-BebasNeue.txt": "72082f6cb4d04be2ecf7cc7d9e1e7d73787f0af8a5a278a47cade70c16b78341",
    "fonts/OFL-BodoniModa.txt": "97e32fdfa86a9aa79b85ce20b63b8618a8bf3e1110a0e631fac7f73983417b55",
    "fonts/OFL-CrimsonText.txt": "50fd67cddc097377a5c871e8452b778bc5aedfa3480a705cb27c5e3a078218df",
    "fonts/OFL-Lato.txt": "74ba064d03f1f1c4a952da936c3eb71866c34404916734de3cae73b34357e59e",
    "fonts/OFL-Montserrat.txt": "8b7141c03fa4f8d44e6345d5d4931709290f0f67875e452e95ac1fd3a027802e",
    "fonts/OFL-PlayfairDisplay.txt": "566be814f8e96e93dfa16101331557eb6b5467e9e03f627c0910fe93ca12300e",
    "fonts/PlayfairDisplay-BoldItalic.ttf": "ea85e419850d4db534e2ffcfaa2edb7fe1a85e13186e6dc5b569d7a83231ac8c",
}


def linha(estado: str, texto: str) -> None:
    print(f"[{estado}] {texto}")


def versao_compativel(instalada: str, minima: str, maxima_exclusiva: str | None = None) -> bool:
    """Compare package versions according to PEP 440, including prereleases."""
    if Version is None:
        return False
    try:
        atual = Version(instalada)
        return atual >= Version(minima) and (
            maxima_exclusiva is None
            or atual.release < Version(maxima_exclusiva).release
        )
    except InvalidVersion:
        return False


def diagnosticar_dependencias() -> int:
    problemas = 0
    python_atual = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 10):
        problemas += 1
        linha(FALHA, f"Python {python_atual}; é necessário Python 3.10 ou mais recente.")
    else:
        linha(OK, f"Python {python_atual} (mínimo 3.10)")

    for dependencia in DEPENDENCIAS:
        modulo, apelido, minima, *limite = dependencia
        maxima_exclusiva = limite[0] if limite else None
        faixa = (
            f"suporte: {minima} até antes da versão {maxima_exclusiva}"
            if maxima_exclusiva else f"mínimo {minima}"
        )
        try:
            importado = __import__(modulo)
            versao = str(getattr(importado, "__version__", "0"))
        except ImportError:
            problemas += 1
            linha(FALHA, f"{apelido} ausente; {faixa}. Rode: python -m pip install .")
            continue
        if versao_compativel(versao, minima, maxima_exclusiva):
            linha(OK, f"{apelido} {versao} ({faixa})")
        else:
            problemas += 1
            linha(FALHA, f"{apelido} {versao}; {faixa}.")
    return problemas


def testar_escrita() -> int:
    try:
        descriptor, caminho = tempfile.mkstemp(prefix=".fanara-fotolivro-verificar-", dir=os.getcwd())
        os.close(descriptor)
        os.unlink(caminho)
        linha(OK, f"permissão de escrita em {os.getcwd()}")
        return 0
    except OSError as erro:
        linha(FALHA, f"sem permissão de escrita em {os.getcwd()}: {erro}")
        return 1


def diagnosticar_fontes() -> int:
    """Report font resolution even when a required runtime package is missing."""
    try:
        from provas import tema
    except Exception as erro:
        linha(AVISO, f"não foi possível diagnosticar fontes: {type(erro).__name__}: {erro}")
        return 0

    print("\nPastas de fontes procuradas:")
    for pasta in tema._pastas_de_fontes():
        marca = "existe" if os.path.isdir(pasta) else "não existe"
        print(f"  {marca:10} {pasta}")

    print("\nFontes escolhidas:")
    papeis = (("título/serifa", tema.SERIF), ("serifa itálica", tema.SERIF_ITALICO),
              ("texto/sem serifa", tema.SANS), ("rótulos", tema.SANS_MEDIO))
    embutidas = 0
    for rotulo, fonte in papeis:
        if fonte.arquivo:
            print(f"  {rotulo:18} {os.path.basename(fonte.arquivo)}")
        else:
            embutidas += 1
            print(f"  {rotulo:18} (usando a fonte PDF embutida '{fonte.embutida}')")
    if embutidas:
        linha(AVISO, f"{embutidas} de 4 papéis sem fonte do sistema; o PDF continua legível.")
    else:
        linha(OK, "todos os papéis com fonte do sistema")

    # As capas editoriais têm tipografia própria, empacotada. Sem ela a capa sai
    # com outra métrica e outro desenho — só se percebe olhando o PDF pronto.
    try:
        from provas.tipografia_capas import familias_ausentes
    except Exception as erro:
        linha(AVISO, f"não foi possível conferir as fontes das capas: {erro}")
        return 0
    ausentes = familias_ausentes()
    if ausentes:
        linha(AVISO, f"capas sem tipografia própria: {', '.join(ausentes)}")
    else:
        linha(OK, "capas editoriais com a tipografia especificada")
    return 0


def diagnosticar_recursos() -> int:
    """Validate every tracked brand/font resource in source and frozen layouts."""
    problemas = 0
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
    for nome, esperado in RECURSOS_OFICIAIS.items():
        path = base / nome
        try:
            atual = sha256(path.read_bytes()).hexdigest()
        except OSError as erro:
            problemas += 1
            linha(FALHA, f"recurso oficial ausente: {nome} ({erro})")
            continue
        if atual != esperado:
            problemas += 1
            linha(FALHA, f"hash inválido do recurso oficial: {nome}")
        else:
            linha(OK, f"recurso oficial verificado: {nome}")
    return problemas


def diagnosticar_cascade(cv2_module=None) -> int:
    """Valide a presença e o carregamento do cascade Haar distribuído pelo OpenCV."""
    try:
        if cv2_module is None:
            import cv2 as cv2_module
        pasta = getattr(getattr(cv2_module, "data", None), "haarcascades", "")
        caminho = os.path.join(pasta, "haarcascade_frontalface_default.xml")
        if not pasta or not os.path.isfile(caminho):
            linha(FALHA, f"cascade Haar local não encontrado: {caminho or '(caminho indisponível)'}")
            return 1
        cascade = cv2_module.CascadeClassifier(caminho)
        if cascade.empty():
            linha(FALHA, f"cascade Haar local não pôde ser carregado: {caminho}")
            return 1
        linha(OK, f"cascade Haar local carregado: {os.path.basename(caminho)}")
        return 0
    except ImportError:
        linha(FALHA, "cascade Haar local não diagnosticado porque o OpenCV está ausente.")
        return 1
    except Exception as erro:
        linha(FALHA, f"falha ao diagnosticar o cascade Haar local: {type(erro).__name__}: {erro}")
        return 1


def testar_pipeline_editorial() -> int:
    """Exercise the same A4-landscape, unrotated editorial export used by the UI."""
    try:
        import pymupdf
        from PIL import Image
        from provas import motor, tema

        with tempfile.TemporaryDirectory(prefix="fanara-fotolivro-pipeline-") as pasta:
            foto = os.path.join(pasta, "amostra.jpg")
            saida = os.path.join(pasta, "amostra.pdf")
            Image.new("RGB", (300, 450), (110, 80, 60)).save(foto, "JPEG")
            config = motor.Config(
                pasta=pasta, saida=saida, modo="fotolivro", paisagem=True,
                girar_horizontais=False, capa_mosaico=False, limite=1,
            )
            plano = motor.analisar_plano(config).plan
            motor.exportar(config, plano)
            with pymupdf.open(saida) as pdf:
                pagina = pdf[0]
                if (not config.paisagem or config.girar_horizontais or pagina.rect.width <= pagina.rect.height
                        or abs(pagina.rect.width - tema.A4_PAISAGEM[0]) > 0.2
                        or abs(pagina.rect.height - tema.A4_PAISAGEM[1]) > 0.2):
                    raise ValueError("PDF não respeitou A4 paisagem sem rotação decorativa")
        linha(OK, "pipeline editorial: PDF A4 paisagem, sem rotação decorativa")
        return 0
    except Exception as erro:
        linha(FALHA, f"pipeline editorial falhou: {type(erro).__name__}: {erro}")
        return 1


def main(_argv: list[str] | None = None) -> int:
    print(f"\n{PRODUCT_NAME} — verificação\n{'-' * 52}")
    print(f"Sistema : {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Python  : {sys.version.split()[0]}\n")

    problemas = diagnosticar_dependencias()
    problemas += diagnosticar_cascade()
    problemas += testar_escrita()
    problemas += diagnosticar_recursos()
    diagnosticar_fontes()
    if problemas:
        linha(AVISO, "pipeline editorial não foi executado enquanto houver dependências pendentes.")
    else:
        problemas += testar_pipeline_editorial()

    if problemas:
        print("\nResolva os itens acima antes de seguir.\n")
        return 1
    print("\nTudo pronto.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
