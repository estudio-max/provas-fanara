"""Uso pela linha de comando, para automatizar ou testar sem abrir a janela.

    python provas_cli.py "C:\\...\\Ensaio Bianca" --por-pagina 6 --amostra
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from provas import capas, motor, tema


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera o PDF de provas de um ensaio.")
    parser.add_argument("pasta", help="pasta com as fotos da sessão")
    parser.add_argument("-o", "--saida", default="", help="caminho do PDF (padrão: dentro da pasta)")
    parser.add_argument("-t", "--titulo", default="", help="título da capa")
    parser.add_argument("-d", "--data", default="", help="data mostrada na capa")
    parser.add_argument("-n", "--por-pagina", type=int, default=4, help="fotos por página")
    parser.add_argument("-q", "--qualidade", choices=list(motor.QUALIDADES), default="normal")
    parser.add_argument("--logo", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       "assets", "logo.png"))
    parser.add_argument("--estudio", default="", help="nome no topo, quando não há logotipo")
    parser.add_argument("--site", default="", help="endereço mostrado no rodapé")
    parser.add_argument("--fundo", default=tema.FUNDO_PADRAO,
                        help="cor de fundo da página, ex.: #16161A ou #F4F2EE")
    parser.add_argument("--opacidade", type=float, default=0.20, help="força da marca d'água")
    parser.add_argument("--deitado", action="store_true", help="A4 na horizontal")
    parser.add_argument("--capa", choices=list(capas.ESTILOS), default="mosaico")
    parser.add_argument("--sem-capa", action="store_true")
    parser.add_argument("--sem-marca", action="store_true", help="não aplicar marca d'água")
    parser.add_argument("--sem-codigos", action="store_true",
                        help="não escrever o nome do arquivo sob a foto")
    parser.add_argument("--album", action="store_true",
                        help="atalho para --sem-marca --sem-codigos")
    parser.add_argument("--sem-girar", action="store_true", help="não girar fotos horizontais")
    parser.add_argument("--subpastas", action="store_true")
    parser.add_argument("--amostra", action="store_true", help="usa só as 12 primeiras fotos")
    args = parser.parse_args()

    config = motor.Config(
        pasta=args.pasta, saida=args.saida, titulo=args.titulo, subtitulo=args.data,
        por_pagina=args.por_pagina, qualidade=args.qualidade, logo=args.logo,
        marca_opacidade=args.opacidade, paisagem=args.deitado,
        estudio=args.estudio, site=args.site, cor_fundo=args.fundo,
        capa_mosaico=not args.sem_capa, estilo_capa=args.capa,
        marca_dagua=not (args.sem_marca or args.album),
        mostrar_codigos=not (args.sem_codigos or args.album),
        girar_horizontais=not args.sem_girar,
        recursivo=args.subpastas, limite=12 if args.amostra else 0,
    )

    ultimo = [""]

    def progresso(feito: int, total: int, mensagem: str) -> None:
        if mensagem != ultimo[0]:
            ultimo[0] = mensagem
            print(f"\r{mensagem:<48}", end="", flush=True)

    try:
        resultado = motor.gerar(config, progresso=progresso)
    except (ValueError, OSError) as erro:
        print(f"\nErro: {erro}", file=sys.stderr)
        return 1

    print(f"\n{resultado.saida}")
    print(f"{resultado.fotos} fotos · {resultado.paginas} páginas")
    for nome, erro in resultado.falhas:
        print(f"  ignorado: {nome} ({erro})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
