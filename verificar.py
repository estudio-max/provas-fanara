"""Diagnóstico do ambiente e do pipeline editorial.

    python verificar.py
"""
from __future__ import annotations

import os
import platform
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OK, FALHA, AVISO = "  ok ", "FALHA", "aviso"
DEPENDENCIAS = (("PIL", "Pillow", "10.0"), ("pymupdf", "PyMuPDF", "1.24"), ("PySide6", "PySide6", "6.7"))


def linha(estado: str, texto: str) -> None:
    print(f"[{estado}] {texto}")


def _partes_versao(valor: str) -> tuple[int, ...]:
    partes = re.findall(r"\d+", valor)
    return tuple(int(parte) for parte in partes) or (0,)


def versao_compativel(instalada: str, minima: str) -> bool:
    """Compare numeric package versions without rejecting local suffixes."""
    atual, exigida = _partes_versao(instalada), _partes_versao(minima)
    tamanho = max(len(atual), len(exigida))
    return atual + (0,) * (tamanho - len(atual)) >= exigida + (0,) * (tamanho - len(exigida))


def diagnosticar_dependencias() -> int:
    problemas = 0
    python_atual = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 10):
        problemas += 1
        linha(FALHA, f"Python {python_atual}; é necessário Python 3.10 ou mais recente.")
    else:
        linha(OK, f"Python {python_atual} (mínimo 3.10)")

    for modulo, apelido, minima in DEPENDENCIAS:
        try:
            importado = __import__(modulo)
            versao = str(getattr(importado, "__version__", "0"))
        except ImportError:
            problemas += 1
            linha(FALHA, f"{apelido} ausente; mínimo {minima}. Rode: python -m pip install Pillow PyMuPDF PySide6")
            continue
        if versao_compativel(versao, minima):
            linha(OK, f"{apelido} {versao} (mínimo {minima})")
        else:
            problemas += 1
            linha(FALHA, f"{apelido} {versao}; mínimo exigido: {minima}.")
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
    problemas += testar_escrita()
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
