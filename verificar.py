"""Diagnóstico do ambiente e do pipeline editorial.

    python verificar.py
"""
from __future__ import annotations

from hashlib import sha256
import os
import platform
import sys
import tempfile

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
    "fonts/BodoniModa[opsz,wght].ttf": "550f5e34ee0a828d7941b1fe9bc58b34e5260d3f33a61532e6d0a0114e79a5cf",
    "fonts/OFL-BodoniModa.txt": "97e32fdfa86a9aa79b85ce20b63b8618a8bf3e1110a0e631fac7f73983417b55",
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
        descriptor, caminho = tempfile.mkstemp(prefix=".fotolivro-verificar-", dir=os.getcwd())
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
    return 0


def diagnosticar_recursos() -> int:
    """Validate every tracked brand/font resource in source and frozen layouts."""
    from provas import recursos

    problemas = 0
    for nome, esperado in RECURSOS_OFICIAIS.items():
        path = recursos.caminho(nome)
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

        with tempfile.TemporaryDirectory(prefix="fotolivro-pipeline-") as pasta:
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
    print(f"\nFotolivro — verificação\n{'-' * 52}")
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
