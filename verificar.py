"""Confere se esta máquina tem tudo o que o Provas precisa.

    python3 verificar.py
    python3 verificar.py "/caminho/de/uma/pasta/de/ensaio"

Sem argumento só diagnostica. Com a pasta de um ensaio, gera também um PDF de
teste com até 8 fotos, que é a prova real de que tudo funciona.
"""
from __future__ import annotations

import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OK, FALHA, AVISO = "  ok ", "FALHA", "aviso"


def linha(estado: str, texto: str) -> None:
    print(f"[{estado}] {texto}")


def main() -> int:
    print(f"\nProvas — verificação\n{'-' * 52}")
    print(f"Sistema : {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Python  : {sys.version.split()[0]}\n")

    problemas = 0

    try:
        import tkinter
        linha(OK, f"tkinter presente (Tk {tkinter.TkVersion})")
        if tkinter.TkVersion < 8.6:
            linha(AVISO, "Tk anterior a 8.6 — a janela pode ficar feia. "
                         "Prefira o Python do python.org.")
    except ImportError:
        problemas += 1
        linha(FALHA, "tkinter ausente. No macOS, instale o Python do python.org; "
                     "no Linux, o pacote python3-tk.")

    for modulo, apelido in (("PIL", "Pillow"), ("pymupdf", "PyMuPDF")):
        try:
            importado = __import__(modulo)
            versao = getattr(importado, "__version__", "?")
            linha(OK, f"{apelido} {versao}")
        except ImportError:
            problemas += 1
            linha(FALHA, f"{apelido} ausente. Rode:  python3 -m pip install Pillow PyMuPDF")

    if problemas:
        print("\nResolva os itens acima antes de seguir.\n")
        return 1

    from provas import tema

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
            print(f"  {rotulo:18} (nenhuma no sistema — usando a embutida "
                  f"'{fonte.embutida}' do PDF)")
    if embutidas:
        linha(AVISO, f"{embutidas} de 4 papéis sem fonte do sistema. O PDF sai correto, "
                     "só com tipografia mais simples.")
    else:
        linha(OK, "todos os papéis com fonte do sistema")

    if len(sys.argv) > 1:
        pasta = sys.argv[1]
        if not os.path.isdir(pasta):
            linha(FALHA, f"não é uma pasta: {pasta}")
            return 1
        from provas import motor
        saida = os.path.join(os.path.expanduser("~"), "provas-teste.pdf")
        print(f"\nGerando PDF de teste a partir de {pasta} …")
        try:
            config = motor.Config(pasta=pasta, saida=saida, titulo="Teste do Provas",
                                  por_pagina=4, qualidade="leve", limite=8,
                                  estilo_capa="destaque", marca_dagua=False)
            resultado = motor.gerar(config)
        except Exception as erro:
            linha(FALHA, f"{type(erro).__name__}: {erro}")
            return 1
        linha(OK, f"{resultado.fotos} fotos em {resultado.paginas} páginas")
        print(f"       {resultado.saida}")
        for nome, erro in resultado.falhas[:5]:
            print(f"       ignorado: {nome} ({erro})")

    print("\nTudo pronto.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
